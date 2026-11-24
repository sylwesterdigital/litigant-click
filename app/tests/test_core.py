import os, tempfile, unittest, io, json, re
from pathlib import Path
from backend.evidence import literal_matches, extract

class ExtractionTests(unittest.TestCase):
    def test_literal(self):
        pages=[{'page':1,'text':'Grievance and performance'},{'page':2,'text':'Dismissal grievance'}]
        found,counts,hits=literal_matches(pages,['GRIEVANCE','dismissal'],'all'); self.assertTrue(found); self.assertEqual(counts,[2,1]); self.assertEqual([h['page'] for h in hits],[1,2]); self.assertFalse(literal_matches(pages,['absent'],'any')[0])
    def test_email(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'original'; p.write_bytes(b'From: hr@example.com\nTo: worker@example.com\nSubject: Grievance\n\nMeeting notes')
            pages,meta,attachments,flags,_=extract(p,'mail.eml'); self.assertIn('Meeting notes',pages[0]['text']); self.assertEqual(meta['Subject'],'Grievance'); self.assertTrue(flags)
    def test_pdf(self):
        import fitz
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'original'; doc=fitz.open(); page=doc.new_page(); page.insert_text((50,50),'Employment grievance evidence'); doc.save(p); doc.close(); pages,*_=extract(p,'sample.pdf'); self.assertIn('grievance',pages[0]['text'])

class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); os.environ['LITIGANT_DATA_DIR']=cls.tmp.name; os.environ['LITIGANT_PRODUCTION']='0'; from backend.app import app; app.config['TESTING']=True; cls.client=app.test_client()
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def test_workflow(self):
        c=self.client; self.assertEqual(c.get('/api/health').json['project'],'litigant-click'); self.assertEqual(c.get('/',headers={'Host':'bad.example'}).status_code,400)
        home=c.get('/'); self.assertEqual(home.status_code,200); token=re.search(rb'name="csrf" value="([a-f0-9]+)"',home.data).group(1).decode()
        self.assertEqual(c.post('/import',data={}).status_code,403)
        response=c.post('/import',data={'csrf':token,'source':'SAR','file':(io.BytesIO(b'Grievance and dismissal'),'evidence.txt')},content_type='multipart/form-data'); self.assertEqual(response.status_code,302)
        self.assertIn(b'Grievance',c.get(response.location).data); self.assertIn(b'evidence.txt',c.get('/?q=grievance%0Adismissal&mode=all').data); self.assertNotIn(b'evidence.txt',c.get('/?q=missing').data)
        self.assertIn(b'evidence.txt',c.get('/search.csv?q=grievance').data); self.assertEqual(c.get('/documents/1/download').data,b'Grievance and dismissal')
        for route in ('/sar','/bundles','/chronology','/assistant'): self.assertEqual(c.get(route).status_code,200)
        self.assertEqual(c.post('/assistant',data={'csrf':token,'question':'What grievance?' }).status_code,200)
        self.assertEqual(c.post('/bundles',data={'csrf':token,'name':'Test','doc':'1'}).status_code,302); self.assertIn(b'Test',c.get('/bundles').data)
        self.assertEqual(c.post('/chronology',data={'csrf':token,'doc':'1','page':'1','date':'2025-01-01','description':'Example'}).status_code,302)
