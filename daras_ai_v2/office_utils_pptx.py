import typing
import re
import hashlib
import re
from PIL import Image
import io
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.shapes import PP_PLACEHOLDER

from daras_ai.image_input import (
    upload_file_from_bytes,
    gcs_blob_for,
    resize_img_scale,
    delete_blob_from_url,
)
from daras_ai_v2.azure_doc_extract import azure_doc_extract_page_num
from loguru import logger

EMU_TO_PIXELS = 0.000264583  # Conversion factor from EMU to pixels


# TODO use_form_reco
def pptx_to_text_pages(f: typing.BinaryIO, use_form_reco: bool = False) -> list[str]:
    """
    Extracts text, tables, charts, grouped shapes, and images from a PPTX file into Markdown format.
    Combines images into a single collage while preserving positions, dimensions, and cropping.
    """
    prs = Presentation(f)
    slides_text = []

    for slide_num, slide in enumerate(prs.slides, start=1):
        slide_content = [f"\nSlide {slide_num}: "]
        images_and_positions = []

        # Slide dimensions in pixels
        slide_width = int(prs.slide_width * EMU_TO_PIXELS)
        slide_height = int(prs.slide_height * EMU_TO_PIXELS)

        # Collect all images and their positions
        for shape in slide.shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                try:
                    image_stream = io.BytesIO(shape.image.blob)
                    img = Image.open(image_stream)

                    # Apply cropping
                    cropped_img = apply_cropping(img, shape)

                    # Get position and dimensions (convert from EMU to pixels)
                    position = {
                        "left": int(shape.left * EMU_TO_PIXELS),
                        "top": int(shape.top * EMU_TO_PIXELS),
                        "width": int(shape.width * EMU_TO_PIXELS),
                        "height": int(shape.height * EMU_TO_PIXELS),
                    }

                    images_and_positions.append((cropped_img, position))
                except Exception as e:
                    logger.debug(f"Error processing image: {e}")

        # Create collage if images are present
        if images_and_positions:
            try:
                collage = create_positioned_collage(
                    images_and_positions, slide_width, slide_height
                )

                # Convert collage to bytes
                with io.BytesIO() as output:
                    collage.save(output, format="PNG")
                    collage_bytes = output.getvalue()

                slide_content.extend(handle_pictures(collage_bytes))

            except Exception as e:
                logger.debug(f"Error creating collage: {e}")

        # Process other shapes
        for shape in slide.shapes:
            try:
                if shape.has_text_frame:
                    slide_content.extend(handle_text_elements(shape))

                if shape.has_table:
                    slide_content.extend(handle_tables(shape))

                if shape.has_chart:
                    slide_content.extend(handle_charts(shape))

                if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                    slide_content.extend(handle_grouped_shapes(shape))

            except Exception as e:
                slide_content.append(f"  Error processing shape: {e}")

        slides_text.append("\n".join(slide_content))
    return slides_text


def apply_cropping(img: Image.Image, shape) -> Image.Image:
    """
    Applies cropping to an image based on the cropping information in the PowerPoint shape.
    """
    # Retrieve cropping percentages
    crop_left = shape.crop_left
    crop_right = shape.crop_right
    crop_top = shape.crop_top
    crop_bottom = shape.crop_bottom

    # Calculate crop box in pixels
    img_width, img_height = img.size
    left = crop_left * img_width
    right = img_width - (crop_right * img_width)
    top = crop_top * img_height
    bottom = img_height - (crop_bottom * img_height)

    # Crop the image
    cropped_img = img.crop((int(left), int(top), int(right), int(bottom)))
    return cropped_img


def create_positioned_collage(
    images_and_positions: list[tuple[Image.Image, dict]], slide_width, slide_height
):
    """
    Creates a collage where images are placed at their exact positions and dimensions.
    """
    # Create a blank canvas matching the slide dimensions
    canvas = Image.new("RGBA", (slide_width, slide_height), (255, 255, 255, 0))

    for img, pos in images_and_positions:
        # Resize the image to fit the specified dimensions
        resized_img = img.resize((pos["width"], pos["height"]), Image.LANCZOS)
        # Paste the resized image at the specified position
        canvas.paste(resized_img, (pos["left"], pos["top"]))

    return canvas


def handle_text_elements(shape) -> list[str]:
    """
    Handles text elements within a shape, including lists.
    """
    text_elements = []
    is_a_list = False
    is_list_group_created = False
    enum_list_item_value = 0
    bullet_type = "None"
    list_label = "LIST"
    namespaces = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}

    # Identify if shape contains lists
    for paragraph in shape.text_frame.paragraphs:
        p = paragraph._element
        if p.find(".//a:buChar", namespaces=namespaces) is not None:
            bullet_type = "Bullet"
            is_a_list = True
        elif p.find(".//a:buAutoNum", namespaces=namespaces) is not None:
            bullet_type = "Numbered"
            is_a_list = True
        else:
            is_a_list = False

        if paragraph.level > 0:
            is_a_list = True

        if is_a_list:
            if bullet_type == "Numbered":
                list_label = "ORDERED_LIST"

    # Iterate through paragraphs to build up text
    for paragraph in shape.text_frame.paragraphs:
        p = paragraph._element
        enum_list_item_value += 1
        inline_paragraph_text = ""
        inline_list_item_text = ""
        doc_label = "PARAGRAPH"

        for e in p.iterfind(".//a:r", namespaces=namespaces):
            if len(e.text.strip()) > 0:
                e_is_a_list_item = False
                is_numbered = False
                if p.find(".//a:buChar", namespaces=namespaces) is not None:
                    bullet_type = "Bullet"
                    e_is_a_list_item = True
                elif p.find(".//a:buAutoNum", namespaces=namespaces) is not None:
                    bullet_type = "Numbered"
                    is_numbered = True
                    e_is_a_list_item = True
                else:
                    e_is_a_list_item = False

                if e_is_a_list_item:
                    if len(inline_paragraph_text) > 0:
                        text_elements.append(inline_paragraph_text)
                    inline_list_item_text += e.text
                else:
                    if shape.is_placeholder:
                        placeholder_type = shape.placeholder_format.type
                        if placeholder_type in [
                            PP_PLACEHOLDER.CENTER_TITLE,
                            PP_PLACEHOLDER.TITLE,
                        ]:
                            doc_label = "TITLE"
                        elif placeholder_type == PP_PLACEHOLDER.SUBTITLE:
                            doc_label = "SECTION_HEADER"
                    enum_list_item_value = 0
                    inline_paragraph_text += e.text

        if len(inline_paragraph_text) > 0:
            text_elements.append(inline_paragraph_text)

        if len(inline_list_item_text) > 0:
            enum_marker = ""
            if is_numbered:
                enum_marker = str(enum_list_item_value) + "."
            if not is_list_group_created:
                is_list_group_created = True
            text_elements.append(f"{enum_marker} {inline_list_item_text}")

    return text_elements


def handle_tables(shape) -> list[str]:
    """
    Handles tables within a shape, converting them into Markdown format.
    """

    if not hasattr(shape, "has_table") or not shape.has_table:
        return []
    table = shape.table
    table_xml = shape._element

    num_rows = len(table.rows)
    num_cols = len(table.columns)
    grid = [["" for _ in range(num_cols)] for _ in range(num_rows)]

    for row_idx, row in enumerate(table.rows):

        for col_idx, cell in enumerate(row.cells):
            cell_xml = table_xml.xpath(
                f".//a:tbl/a:tr[{row_idx + 1}]/a:tc[{col_idx + 1}]"
            )
            if not cell_xml:
                continue

            cell_xml = cell_xml[0]
            row_span = int(cell_xml.get("rowSpan", 1))
            col_span = int(cell_xml.get("gridSpan", 1))

            # Place text in the grid
            # remove newline char to prevserve table structure
            cleaned_text = re.sub(r"[\n\r]", "", cell.text)
            grid[row_idx][col_idx] = cleaned_text

            # Mark spanned cells
            for i in range(row_span):
                for j in range(col_span):
                    if i == 0 and j == 0:
                        continue
                    if row_idx + i < num_rows and col_idx + j < num_cols:
                        grid[row_idx + i][col_idx + j] = ""

    # Convert grid to Markdown format
    table_text = []
    header = "|" + "|".join(grid[0]) + "|"
    separator = "|" + "---|" * num_cols
    table_text.append(header)
    table_text.append(separator)
    for row in grid[1:]:
        line = "|" + "|".join(row) + "|"
        table_text.append(line)
        print(line)

    return table_text


def handle_grouped_shapes(shape) -> list[str]:
    """
    Formats grouped shapes into Markdown.
    """
    group_text = []

    def handle_shapes(shape):
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            for grouped_shape in shape.shapes:
                handle_shapes(grouped_shape)
        else:
            if shape.has_text_frame:
                group_text.extend(handle_text_elements(shape))

    handle_shapes(shape)
    return group_text


def handle_charts(shape) -> list[str]:
    """
    Handles charts within a shape, converting them into Markdown format.
    """
    chart = shape.chart
    chart_title = chart.chart_title.text_frame.text if chart.has_title else "Chart"
    chart_text = [f" {chart_title}:"]
    for series in chart.series:
        series_text = f"Series '{series.name}'"
        chart_text.append(series_text)
    return chart_text


# TODO :azure form reco to extract text from images
def handle_pictures(image_bytes) -> list[str]:

    image_hash = hashlib.sha256(image_bytes[:64]).hexdigest()
    unique_filename = f"{image_hash}.png"

    logger.debug(f"Extracting text from image: {unique_filename}")

    # Resize the image bytes before uploading
    target_size = (800, 600)
    resized_image_bytes = resize_img_scale(image_bytes, target_size)

    # Upload image and get the URL
    image_url = upload_file_from_bytes(unique_filename, resized_image_bytes)
    logger.debug(f"Uploaded image to: {image_url}")

    extracted_text = azure_doc_extract_page_num(
        image_url, page_num=1, model_id="prebuilt-read"
    )
    logger.debug(f"Extracted text from image: {extracted_text}")

    delete_blob_from_url(image_url)
    logger.debug(f"Deleted image from GCS: {unique_filename}")

    return [extracted_text]
