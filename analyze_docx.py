
import zipfile
import re
import os

docx_path = 'e:\\Python\\Flowwaccount_3\\example.docx'

def analyze():
    if not os.path.exists(docx_path):
        print("File not found.")
        return

    with zipfile.ZipFile(docx_path) as z:
        # We need to find drawings and their positions
        # Structure: <w:drawing> ... <wp:positionH> ... <wp:posOffset>X</wp:posOffset> ... <wp:positionV> ... <wp:posOffset>Y</wp:posOffset> ... <w:txbxContent> ... <w:t>TEXT</w:t>
        
        xml = z.read('word/document.xml').decode('utf-8')

        # Regex to find drawings (this is tricky with regex, but let's try to capture blocks)
        # We'll split by <w:drawing>
        parts = xml.split('<w:drawing>')
        
        items = []
        
        for part in parts[1:]: # Skip first chunk before any drawing
            # Find X offset
            x_match = re.search(r'<wp:positionH.*?<wp:posOffset>(\d+)</wp:posOffset>', part, re.DOTALL)
            x = int(x_match.group(1)) if x_match else 0
            
            # Find Y offset
            y_match = re.search(r'<wp:positionV.*?<wp:posOffset>(\d+)</wp:posOffset>', part, re.DOTALL)
            y = int(y_match.group(1)) if y_match else 0
            
            # Find Text
            # We only care if there is text
            if '<w:t>' in part:
                 # Clean text
                texts = re.findall(r'<w:t>(.*?)</w:t>', part)
                full_text = ''.join(texts).strip()
                if full_text:
                    items.append({'x': x, 'y': y, 'text': full_text})
        
        # Sort by Y then X
        # Emu units: 360000 = 1 cm? No 914400 EMUs = 1 inch?
        # Just relative sorting is enough
        items.sort(key=lambda k: (k['y'], k['x']))
        
        print(f"Found {len(items)} positioned items.")
        print("\n--- VISUAL LAYOUT (Top-Down) ---")
        
        current_y = -1
        row_text = []
        
        for item in items:
            # Group by approximate Y (allow slight variance)
            if current_y == -1 or item['y'] > current_y + 200000: # New line threshold
                if row_text:
                    print('   '.join(row_text))
                row_text = [item['text']]
                current_y = item['y']
            else:
                row_text.append(item['text'])
                
        if row_text:
            print('   '.join(row_text))

if __name__ == "__main__":
    analyze()
