import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk, ImageGrab
import json

class BoundingBoxViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("Visualiseur découpage")
        self.root.geometry("1200x800")

        self.image = None
        self.photo = None

        # Interface layout
        # Left panel for controls and text input
        self.left_frame = tk.Frame(self.root, width=350)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        # Right panel to display the image
        self.right_frame = tk.Frame(self.root)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # JSON text area
        tk.Label(self.left_frame, text="1. Paste JSON result here:", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))
        self.text_area = tk.Text(self.left_frame, wrap=tk.WORD, width=40, height=20)
        self.text_area.pack(fill=tk.Y, expand=True)

        # Button to paste the image
        tk.Label(self.left_frame, text="2. Copy an image (Ctrl+C on the image)", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(15, 5))
        self.btn_paste_img = tk.Button(self.left_frame, text="Paste Image (Clipboard)", command=self.paste_image, height=2)
        self.btn_paste_img.pack(fill=tk.X)

        # Button to draw bounding boxes
        tk.Label(self.left_frame, text="3. Display the result", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(15, 5))
        self.btn_draw = tk.Button(self.left_frame, text="Draw Rectangles", command=self.draw_boxes, bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), height=2)
        self.btn_draw.pack(fill=tk.X)

        # Image area (Canvas) with scrollbars
        self.canvas_frame = tk.Frame(self.right_frame)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.vbar = tk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL)
        self.vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.hbar = tk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL)
        self.hbar.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas = tk.Canvas(self.canvas_frame, bg="#e0e0e0", xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.vbar.config(command=self.canvas.yview)
        self.hbar.config(command=self.canvas.xview)

    def paste_image(self):
        """Retrieves the image from the computer's clipboard."""
        try:
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                self.image = img
                self.display_image()
            else:
                messagebox.showwarning("Warning", "The clipboard does not contain an image. Copy an image first")
        except Exception as e:
            messagebox.showerror("Error", f"Unable to paste image: {e}")

    def display_image(self):
        """Displays the raw image on the canvas."""
        if self.image:
            self.photo = ImageTk.PhotoImage(self.image)
            self.canvas.delete("all")
            self.canvas.config(scrollregion=(0, 0, self.photo.width(), self.photo.height()))
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

    def draw_boxes(self):
        """Reads the JSON data and draws red rectangles on the image."""
        if not self.image:
            messagebox.showwarning("Warning", "Please paste an image first.")
            return

        json_text = self.text_area.get("1.0", tk.END).strip()
        if not json_text:
            messagebox.showwarning("Warning", "Please paste the JSON code.")
            return

        try:
            data = json.loads(json_text)
            self.display_image() # Reload the clean image to clear previous drawings
            
            for item in data:
                x0 = item.get("xDépart")
                y0 = item.get("yDépart")
                x1 = item.get("xFin")
                y1 = item.get("yFin")
                
                # Ensure all coordinates exist
                if all(v is not None for v in [x0, y0, x1, y1]):
                    self.canvas.create_rectangle(x0, y0, x1, y1, outline="red", width=3)
                    
        except json.JSONDecodeError:
            messagebox.showerror("Error", "The pasted text is not a valid JSON.")
        except Exception as e:
            messagebox.showerror("Error", f"Error: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = BoundingBoxViewer(root)
    root.mainloop()