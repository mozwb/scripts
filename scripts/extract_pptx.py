"""
PPTX 文字提取工具
用法: python extract_pptx.py <path/to/file.pptx>
提取所有幻灯片中的文本内容，打印到控制台
"""
import zipfile, os, glob, re, sys

def extract_pptx_text(pptx_path):
    out_dir = '_pptx_tmp'
    os.makedirs(out_dir, exist_ok=True)
    
    with zipfile.ZipFile(pptx_path, 'r') as z:
        z.extractall(out_dir)
    
    slide_files = sorted(glob.glob(os.path.join(out_dir, 'ppt/slides/slide*.xml')))
    for sf in slide_files:
        with open(sf, 'r', encoding='utf-8') as f:
            content = f.read()
        texts = re.findall(r'<a:t[^>]*>([^<]+)</a:t>', content)
        if texts:
            print(f'=== {os.path.basename(sf)} ===')
            for t in texts:
                print(t)
            print()
    
    import shutil
    shutil.rmtree(out_dir, ignore_errors=True)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python extract_pptx.py <file.pptx>')
        sys.exit(1)
    extract_pptx_text(sys.argv[1])
