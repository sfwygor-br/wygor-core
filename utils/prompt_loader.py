import os

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")

def load_prompt(template_name: str, **kwargs) -> str:
    """Carrega um arquivo de template de prompt e substitui as variáveis informadas.

    Usa substituição segura (str.replace) em vez de str.format() para não quebrar
    templates que contêm JSON/objetos com chaves {} (ex.: exemplos nos prompts).
    Substitui apenas os placeholders conhecidos, na ordem do nome mais longo para
    o mais curto (evita colisões parciais, ex.: {user} vs {user_name}).
    """
    file_path = os.path.join(PROMPTS_DIR, template_name)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Template de prompt '{template_name}' não encontrado em: {PROMPTS_DIR}")
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    for key in sorted(kwargs.keys(), key=len, reverse=True):
        content = content.replace("{" + key + "}", str(kwargs[key]))
    return content