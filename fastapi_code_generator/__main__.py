from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional
import itertools
import typer
from datamodel_code_generator import InputFileType, PythonVersion
from datamodel_code_generator import generate as generate_models
from datamodel_code_generator.format import format_code
from jinja2 import Environment, FileSystemLoader
from collections import defaultdict
from datamodel_code_generator.imports import Import, Imports

from fastapi_code_generator.parser import OpenAPIParser, Operation, ParsedObject

app = typer.Typer()

BUILTIN_TEMPLATE_DIR = Path(__file__).parent / "template"
CONTROLLERS_DIR_NAME = 'routers'


@app.command()
def main(
    input_file: typer.FileText = typer.Option(..., "--input", "-i"),
    output_dir: Path = typer.Option(..., "--output", "-o"),
    template_dir: Optional[Path] = typer.Option(None, "--template-dir", "-t"),
) -> None:
    input_name: str = input_file.name
    input_text: str = input_file.read()
    return generate_code(input_name, input_text, output_dir, template_dir)


def generate_controllers_code(environment, parsed_object) -> Dict:
    results: Dict[Path, str] = {}
    template_path = Path('controller.jinja2')
    # group by path
    grouped_operations = defaultdict(list)
    for k, g in itertools.groupby(parsed_object.operations, key=lambda x: x.path.strip('/').split('/')[0]):
        grouped_operations[k] += list(g)
    # render each group in separate file
    for name, operations in grouped_operations.items():
        result = environment.get_template(str(template_path)).render(
            operations=operations, imports=parsed_object.imports, name=name
        )
        results[Path(name)] = format_code(result, PythonVersion.PY_38)
    return results


def generate_app_code(environment, parsed_object) -> str:
    template_path = Path('main.jinja2')
    grouped_operations = defaultdict(list)
    for k, g in itertools.groupby(parsed_object.operations, key=lambda x: x.path.strip('/').split('/')[0]):
        grouped_operations[k] += list(g)

    imports = Imports()
    routers = []
    for name, operations in grouped_operations.items():
        imports.append(Import(
                            from_=CONTROLLERS_DIR_NAME + '.' + name, import_=name + '_router'
                        ))

        routers.append(name + '_router')
    result = environment.get_template(str(template_path)).render(
        imports=imports, routers=routers,
    )

    return result


def generate_code(
    input_name: str, input_text: str, output_dir: Path, template_dir: Optional[Path]
) -> None:
    if not output_dir.exists():
        output_dir.mkdir(parents=True)
    if not template_dir:
        template_dir = BUILTIN_TEMPLATE_DIR
    parser = OpenAPIParser(input_name, input_text)
    parsed_object: ParsedObject = parser.parse()

    environment: Environment = Environment(
        loader=FileSystemLoader(
            template_dir if template_dir else f"{Path(__file__).parent}/template",
            encoding="utf8",
        ),
    )

    controllers_code = generate_controllers_code(environment, parsed_object)

    main_app_code = generate_app_code(environment, parsed_object)

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    header = f"""\
# generated by fastapi-codegen:
#   filename:  {Path(input_name).name}
#   timestamp: {timestamp}"""

    controllers_dir = output_dir.joinpath(CONTROLLERS_DIR_NAME)
    if not controllers_dir.exists():
        controllers_dir.mkdir()
    with controllers_dir.joinpath(Path('__init__.py')).open("wt") as file:
        print('', file=file)
    for path, code in controllers_code.items():
        with controllers_dir.joinpath(path.with_suffix(".py")).open("wt") as file:
            print(header, file=file)
            print("", file=file)
            print(code.rstrip(), file=file)

    with output_dir.joinpath(Path('main').with_suffix(".py")).open('wt') as file:
        print(main_app_code, file=file)

    generate_models(
        input_name=input_name,
        input_text=input_text,
        input_file_type=InputFileType.OpenAPI,
        output=output_dir.joinpath("models.py"),
        target_python_version=PythonVersion.PY_38,
        aliases={'schema': 'scheme'},
    )


if __name__ == "__main__":
    typer.run(main)
