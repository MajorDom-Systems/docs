"""Render an OpenAPI spec as compact markdown for ``llms-full.txt``.

One block per operation (description, parameters, body, responses with their explicit examples), then one
per schema. Samples Swagger UI would generate from the schemas are left out: the schema blocks carry them.
"""

from __future__ import annotations

import json
from typing import Any

type Json = dict[str, Any]


def _oneline(text: str) -> str:
    return " ".join(text.split())


class _Renderer:
    def __init__(self, spec: Json):
        self.spec = spec
        self.schemas: Json = spec.get("components", {}).get("schemas", {})

    def type_of(self, schema: Json) -> str:
        if ref := schema.get("$ref"):
            name = ref.rsplit("/", 1)[-1]
            return f"`{self.schemas.get(name, {}).get('title', name)}`"
        for key in ("anyOf", "oneOf"):
            if key in schema:
                return " | ".join(self.type_of(option) for option in schema[key])
        if "const" in schema:
            return f"`{schema['const']}`"
        if "enum" in schema:
            return " | ".join(f"`{value}`" for value in schema["enum"])
        if schema.get("type") == "array":
            return f"list[{self.type_of(schema.get('items', {}))}]"
        if schema.get("type") == "object" and isinstance(schema.get("additionalProperties"), dict):
            return f"dict[str, {self.type_of(schema['additionalProperties'])}]"
        return schema.get("format") or schema.get("type", "any")

    def body_of(self, content: Json) -> str:
        return self.type_of(next(iter(content.values())).get("schema", {})) if content else ""

    @staticmethod
    def examples_of(content: Json) -> list[str]:
        media = next(iter(content.values()), {}) if content else {}
        examples = {name: example.get("value") for name, example in media.get("examples", {}).items()}
        if "example" in media:
            examples["example"] = media["example"]
        return [f"  - `{name}`: `{json.dumps(value, separators=(', ', ': '))}`" for name, value in examples.items()]

    def operation(self, method: str, path: str, op: Json) -> list[str]:
        lines = [f"## {method.upper()} {path}"]
        if description := op.get("description") or op.get("summary"):
            lines += ["", _oneline(description)]
        if params := op.get("parameters"):
            rendered = (
                f"`{p['name']}` ({p['in']}{', required' if p.get('required') else ''}): {self.type_of(p.get('schema', {}))}"
                for p in params
            )
            lines += ["", "Parameters: " + "; ".join(rendered)]
        if request := op.get("requestBody"):
            lines += ["", f"Body: {self.body_of(request.get('content', {}))}"]
        lines += ["", "Responses:"]
        for code, response in op.get("responses", {}).items():
            content = response.get("content", {})
            line = f"- {code} {self.body_of(content)}".rstrip()
            description = _oneline(response.get("description", ""))
            if description and description not in ("Successful Response", "Validation Error"):
                line += f": {description}"
            lines += [line, *self.examples_of(content)]
        return [*lines, ""]

    def schema(self, name: str, schema: Json) -> list[str]:
        lines = [f"## {schema.get('title', name)}"]
        if description := schema.get("description"):
            lines.append(_oneline(description))
        if "enum" in schema:
            lines.append("One of: " + ", ".join(f"`{value}`" for value in schema["enum"]))
        required = set(schema.get("required", []))
        for field, prop in schema.get("properties", {}).items():
            line = f"- `{field}`: {self.type_of(prop)}{', required' if field in required else ''}"
            if "default" in prop:
                line += f", default `{json.dumps(prop['default'])}`"
            if description := prop.get("description"):
                line += f". {_oneline(description)}"
            lines.append(line)
        return [*lines, ""]

    def render(self, title: str) -> str:
        lines = [f"# {title}", ""]
        for path, operations in self.spec.get("paths", {}).items():
            for method, op in operations.items():
                lines += self.operation(method, path, op)
        lines += ["# Schemas", ""]
        for name, schema in self.schemas.items():
            lines += self.schema(name, schema)
        return "\n".join(lines)


def render(spec: Json, title: str) -> str:
    return _Renderer(spec).render(title)
