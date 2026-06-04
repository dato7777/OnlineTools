from app.schemas import ToolInfo
from app.tools.base import ToolHandler
from app.tools.pdf_editor import pdf_editor_tool

_TOOLS: dict[str, ToolHandler] = {
    pdf_editor_tool.slug: pdf_editor_tool,
}

_COMING_SOON = [
    ToolInfo(
        slug="pdf-merge",
        title="Merge PDF",
        description="Combine multiple PDFs into one document.",
        icon="files",
        input_mime_types=["application/pdf"],
        enabled=False,
        coming_soon=True,
    ),
    ToolInfo(
        slug="compress-pdf",
        title="Compress PDF",
        description="Reduce file size while keeping readability.",
        icon="minimize-2",
        input_mime_types=["application/pdf"],
        enabled=False,
        coming_soon=True,
    ),
    ToolInfo(
        slug="pdf-to-docx",
        title="PDF to Word",
        description="Convert PDF to editable DOCX.",
        icon="file-output",
        input_mime_types=["application/pdf"],
        enabled=False,
        coming_soon=True,
    ),
    ToolInfo(
        slug="images-to-pdf",
        title="Images to PDF",
        description="Turn JPG and PNG images into a PDF.",
        icon="image",
        input_mime_types=["image/jpeg", "image/png"],
        enabled=False,
        coming_soon=True,
    ),
]


def get_tool(slug: str) -> ToolHandler | None:
    return _TOOLS.get(slug)


def list_tools() -> list[ToolInfo]:
    items: list[ToolInfo] = []
    for tool in _TOOLS.values():
        items.append(
            ToolInfo(
                slug=tool.slug,
                title=tool.title,
                description=tool.description,
                icon=tool.icon,
                input_mime_types=tool.input_mime_types,
                enabled=True,
                coming_soon=False,
            )
        )
    items.extend(_COMING_SOON)
    return items
