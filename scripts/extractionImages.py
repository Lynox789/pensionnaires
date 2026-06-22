import os
import fitz  # PyMuPDF module (install -> pip install PyMuPDF)

def extract_pdf_pages():
    # Ask user for PDF file
    pdf_path = input("Enter the PDF file name/path: ")
    
    # Check file existence
    if not os.path.exists(pdf_path):
        print(f"Error: File '{pdf_path}' not found.")
        return

    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_dir = "images"
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    print(f"Opening {pdf_path}...")
    doc = fitz.open(pdf_path)

    converted_count = 0
    image_counter = 1

    # Process each page
    for i in range(len(doc)):
        page_num = i + 1
        
        # Skip page 1 for all PDFs
        if page_num == 1:
            continue
            
        # Skip page 2 for specific PDFs
        if page_num == 2 and base_name in ["1", "2", "3", "4"]:
            continue

        # Convert page to image
        page = doc.load_page(i)
        pix = page.get_pixmap(dpi=150) 
        
        # Format and save image
        image_name = f"{base_name}_{image_counter:03d}.png"
        image_path = os.path.join(output_dir, image_name)
        
        pix.save(image_path)
        converted_count += 1
        image_counter += 1

        print(f"Saved {image_name}")

    doc.close()
    print(f"\nDone! {converted_count} pages converted in '{output_dir}'.")

if __name__ == "__main__":
    extract_pdf_pages()