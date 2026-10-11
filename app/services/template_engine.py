import re

VARIABLE_PATTERN = re.compile(r"{{\s*(\w+)\s*}}")

class TemplateEngine:
    @staticmethod
    def extract_placeholders(template: str):
        return set(VARIABLE_PATTERN.findall(template))

    @staticmethod
    def render(template: str, context: dict[str, str]):
        def replace(match):
            key = match.group(1)
            if key not in context:
                raise ValueError(f"Missing value for placeholder: {key}")
            return str(context[key])
        return VARIABLE_PATTERN.sub(replace, template)
