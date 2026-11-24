import logging, time, hashlib, io, re, subprocess, tempfile, shutil, zipfile
from pathlib import Path
from email import policy
from email.parser import BytesParser
import fitz
from PIL import Image, ImageOps
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation

LOG=logging.getLogger('litigant.extraction')
MAX_PAGES=5000
MAX_TEXT=2_000_000
Image.MAX_IMAGE_PIXELS=40_000_000

def ocr(image):
    if not shutil.which('tesseract'):
        LOG.warning('OCR unavailable: Tesseract not found'); return '', 'OCR unavailable: install Tesseract'
    started=time.monotonic(); LOG.info('OCR start')
    try:
        p=subprocess.run(['tesseract','stdin','stdout','-l','eng'],input=image,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=45)
        LOG.log(logging.INFO if p.returncode==0 else logging.WARNING,'OCR complete exit=%d elapsed=%.2fs',p.returncode,time.monotonic()-started)
        return p.stdout.decode('utf-8','replace')[:MAX_TEXT], 'OCR (unverified)' if p.returncode==0 else 'OCR failed'
    except subprocess.TimeoutExpired:
        LOG.warning('OCR timed out'); return '', 'OCR timed out'

def possible_dark_bar(image):
    # Conservative heuristic: dark, nearly solid horizontal rectangle, not proof of redaction.
    im=image.convert('L'); im.thumbnail((800,800)); w,h=im.size; data=im.load(); previous=None; height=0
    if w<100 or h<50: return False
    for y in range(h):
        spans=[]; start=None
        for x in range(w):
            if data[x,y]<24:
                if start is None: start=x
            elif start is not None:
                if x-start>=max(28,w*.07): spans.append((start,x))
                start=None
        if start is not None and w-start>=max(28,w*.07): spans.append((start,w))
        if spans:
            span=max(spans,key=lambda a:a[1]-a[0]);
            if previous and abs(span[0]-previous[0])<=2 and abs(span[1]-previous[1])<=2: height+=1
            else: height=1
            previous=span
            if 4<=height<=max(8,h*.08) and span[1]-span[0]>=height*4 and span[0]>2 and span[1]<w-2: return True
        else: previous=None; height=0
    return False

def inspect_pdf(path):
    pages=[]
    with fitz.open(path) as pdf:
        if pdf.is_encrypted: raise ValueError('Encrypted PDF: unlock a copy separately')
        if len(pdf)>MAX_PAGES: raise ValueError('PDF page limit exceeded')
        LOG.info('PDF extraction start pages=%d',len(pdf))
        for page in pdf:
            LOG.info('PDF page %d/%d',page.number+1,len(pdf))
            text=page.get_text()[:MAX_TEXT]; flags=[]; method='native PDF'
            if len(text.strip())<25 and page.get_images():
                flags.append('Image-based page; possible scan or screenshot')
                scale=min(2, 1800/max(page.rect.width,page.rect.height,1))
                png=page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).tobytes('png'); text,method=ocr(png)
                with Image.open(io.BytesIO(png)) as image:
                    if possible_dark_bar(image): flags.append('Dark horizontal region; possible redaction or interface element')
            for drawing in page.get_drawings():
                fill=drawing.get('fill'); rect=drawing.get('rect')
                if fill and max(fill)<0.13 and rect and rect.width>25 and 5<rect.height<100:
                    flags.append('Dark rectangle; possible redaction (review required)'); break
            if not text.strip(): flags.append('No searchable text extracted')
            pages.append({'text':text,'method':method,'flags':flags})
    return pages

def check_office(path):
    with zipfile.ZipFile(path) as z:
        entries=z.infolist()
        if len(entries)>15000 or sum(e.file_size for e in entries)>250*1024*1024: raise ValueError('Office archive exceeds safety limit')

def extract(path, name):
    ext=Path(name).suffix.lower(); meta={}; attachments=[]; flags=[]; preview=None
    if ext=='.pdf': return inspect_pdf(path),meta,attachments,flags,Path(path)
    if ext in ('.png','.jpg','.jpeg','.tif','.tiff','.webp','.bmp'):
        pages=[]
        with Image.open(path) as im:
            for i in range(min(getattr(im,'n_frames',1),500)):
                im.seek(i); image=ImageOps.exif_transpose(im).convert('RGB'); image.thumbnail((2400,2400)); b=io.BytesIO(); image.save(b,'PNG'); text,method=ocr(b.getvalue())
                image_flags=['Image; original source/context not established']+([] if text.strip() else ['No searchable text extracted'])
                if possible_dark_bar(image): image_flags.append('Dark horizontal region; possible redaction or interface element')
                pages.append({'text':text,'method':method,'flags':image_flags})
        return pages,meta,attachments,flags,None
    if ext=='.eml':
        msg=BytesParser(policy=policy.default).parsebytes(Path(path).read_bytes())
        for h in ('From','To','Cc','Date','Subject','Message-ID','In-Reply-To','References'): meta[h]=str(msg.get(h,''))
        if not all(meta[h] for h in ('From','To','Date','Message-ID')): flags.append('One or more email headers absent')
        body=msg.get_body(preferencelist=('plain','html')); content=body.get_content() if body else ''
        if body and body.get_content_type()=='text/html':
            from html.parser import HTMLParser
            class Text(HTMLParser):
                parts=[]
                def handle_data(self,data): self.parts.append(data)
            parser=Text(); parser.feed(content); content=' '.join(parser.parts)
        text='\n'.join(f'{k}: {v}' for k,v in meta.items())+'\n\n'+str(content)
        for part in msg.iter_attachments():
            payload=part.get_payload(decode=True)
            if payload is not None and len(payload)<=100*1024*1024: attachments.append((part.get_filename() or 'attachment.bin',payload))
        meta['attachments']=[a[0] for a in attachments]
    elif ext in ('.doc','.odt','.rtf','.docx','.ppt','.pptx','.xls','.xlsx','.ods'):
        if ext in ('.docx','.pptx','.xlsx','.odt','.ods'): check_office(path)
        if ext=='.docx':
            d=Document(path); text='\n'.join(p.text for p in d.paragraphs)+'\n'+'\n'.join(' | '.join(c.text for c in r.cells) for t in d.tables for r in t.rows)
            meta['author']=d.core_properties.author or ''
        elif ext=='.xlsx':
            w=load_workbook(path,read_only=True,data_only=False); chunks=[]; count=0
            try:
                for s in w:
                    chunks.append('Sheet: '+s.title)
                    for row in s.iter_rows(max_row=min(s.max_row or 10000,10000),max_col=min(s.max_column or 100,100),values_only=True):
                        chunks.append(' | '.join(str(v if v is not None else '') for v in row)); count+=1
                        if count>=20000: break
                    if count>=20000: break
            finally: w.close()
            text='\n'.join(chunks); flags.append('Spreadsheet extraction limited to 20,000 rows / 100 columns per sheet; formulas not evaluated')
        elif ext=='.pptx':
            p=Presentation(path); text='\n'.join(f'Slide {i+1}\n'+'\n'.join(s.text for s in slide.shapes if s.has_text_frame) for i,slide in enumerate(p.slides))
        else:
            text=''; flags.append('Legacy format requires LibreOffice conversion')
        lo=shutil.which('libreoffice') or ('/Applications/LibreOffice.app/Contents/MacOS/soffice' if Path('/Applications/LibreOffice.app/Contents/MacOS/soffice').exists() else None)
        if lo:
            with tempfile.TemporaryDirectory() as temp:
                target=Path(temp)/('input'+ext); shutil.copyfile(path,target)
                try:
                    subprocess.run([lo,'-env:UserInstallation='+ (Path(temp)/'profile').as_uri(),'--headless','--convert-to','pdf','--outdir',temp,str(target)],capture_output=True,timeout=90,check=True)
                    converted=Path(temp)/'input.pdf'
                    if converted.exists():
                        data=converted.read_bytes(); pages=inspect_pdf(converted)
                        meta['conversion']='LibreOffice derivative; pagination may differ from original'
                        # retain native text for formats whose layout conversion can omit content
                        if text and ext in ('.docx','.pptx','.xlsx'): meta['native_text_available']=True
                        return pages,meta,attachments,flags,data
                except (OSError,subprocess.SubprocessError,ValueError): flags.append('PDF conversion failed; text extraction only')
    elif ext in ('.txt','.csv','.json','.md','.log','.xml','.html','.htm'):
        text=Path(path).read_bytes().decode('utf-8','replace')
    else: return [],meta,attachments,['Unsupported format; original preserved, not indexed'],None
    if len(text)>MAX_TEXT: flags.append('Extracted text truncated at 2 million characters')
    return [{'text':text[:MAX_TEXT],'method':'extracted text (not original pagination)','flags':[]}] if text.strip() else [],meta,attachments,flags,None


def literal_matches(pages, terms, mode):
    terms=[t.casefold() for t in terms if t]; counts=[0]*len(terms); locations=[]
    for p in pages:
        text=p['text']; folded=text.casefold(); hits=[folded.count(t) for t in terms]
        counts=[a+b for a,b in zip(counts,hits)]
        if any(hits):
            pos=min(folded.find(t) for t in terms if t in folded); locations.append({'page':p['page'],'snippet':text[max(0,pos-80):pos+200],'counts':hits})
    return (not terms or (all(counts) if mode=='all' else any(counts))),counts,locations
