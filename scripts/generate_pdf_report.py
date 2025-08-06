import sys
import json
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright
import markdown2
import re
import plotly.io as pio

def clean_text(text):
    if not text:
        return ""

    frases_a_eliminar = [
        "¿Te gustaría que cree una visualización para estos datos?",
        "No hay un gráfico asociado a esta consulta, pero si lo deseas, puedo generar uno para visualizar mejor la distribución de los hallazgos.",
        "Finalmente, he generado un gráfico de barras para ti.",
        "Se ha generado un gráfico exitosamente. Menciona esto en tu respuesta.",
        "Espero que esta información te sea útil, Natalia.",
        "Si necesitas más detalles o quieres discutir alguna de estas puntos, no dudes en preguntar.",
        # Puedes añadir aquí más frases molestas de cierre/conversacionales...
    ]
    for frase in frases_a_eliminar:
        text = text.replace(frase, "")

    # Elimina TODAS las líneas que sean solo títulos de Markdown (# ... hasta ###### ...)
    text = re.sub(r"^\s*#{1,6}\s*.*\n?", "", text, flags=re.MULTILINE)
    # Elimina también títulos tipo "**Resumen Ejecutivo ...**"
    text = re.sub(r"^\s*\*{0,2}Resumen Ejecutivo.*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\*{0,2}Prioridades de Trabajo.*\n?", "", text, flags=re.MULTILINE)
    # Quita líneas en blanco duplicadas
    text = re.sub(r'\n\s*\n+', '\n\n', text)

    return text.strip()


def main():
    if len(sys.argv) != 4:
        print("Usage: generate_pdf_report.py <context_json> <template_path> <output_pdf_path>", file=sys.stderr)
        sys.exit(1)

    context_json = sys.argv[1]
    template_path = sys.argv[2]
    output_pdf_path = sys.argv[3]

    try:
        context = json.loads(context_json)

        for key in ["summary", "recommendations"]:
            if key in context:
                cleaned_text = clean_text(context[key])
                context[key] = markdown2.markdown(cleaned_text)
        
        if context.get("chart_spec"):
            chart_html = pio.to_html(
                context["chart_spec"], 
                full_html=False, 
                include_plotlyjs='cdn', 
                default_height='400px', 
                default_width='100%'
            )
            
            context["chart_spec"] = chart_html

        env = Environment(
            loader=FileSystemLoader(str(Path(template_path).parent)),
            autoescape=select_autoescape(['html', 'xml'])
        )
        template = env.get_template(Path(template_path).name)
        html_content = template.render(context)

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(html_content, wait_until="networkidle")
            page.pdf(
                path=output_pdf_path, 
                format="A4", 
                print_background=True,
                margin={"top": "28px", "right": "28px", "bottom": "28px", "left": "28px"}
            )
            browser.close()
            
    except Exception as e:
        print(f"Error generating PDF: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()