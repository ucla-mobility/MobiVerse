import xml.etree.ElementTree as ET

def filter_polygons():
    # Read the original poly file
    tree = ET.parse('../sumo_config/westwood.poly.xml')
    root = tree.getroot()
    
    # Create new XML for polygons only
    new_root = ET.Element('additional')
    
    # Copy only polygon elements (skip POIs)
    for child in root:
        if child.tag == 'poly':
            new_root.append(child)
    
    # Write to new file
    tree = ET.ElementTree(new_root)
    with open('../sumo_config/westwood.landscape.xml', 'wb') as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding='utf-8')
    
    print("Created landscape file without POIs")

if __name__ == '__main__':
    filter_polygons() 