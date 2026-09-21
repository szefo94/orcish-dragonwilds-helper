"""1.5: learned memory/templates (safety + limits + persistence), confirm count, glyph filter.
Uses synthetic images and no OCR model, so it runs fast anywhere."""
import unittest, tempfile
import cv2, numpy as np
from engine import Controller
from vision import Prompt, keycaps, has_glyph, text_extent
from learn import Learner, Memory, PW, PH, KEY

def scene(label,key,name=None,seed=0,bright=110,x=640,y=150,sz=.9):
    rng=np.random.default_rng(seed)
    bg=cv2.resize(rng.integers(15,bright,(40,90,3)).astype(np.uint8),(900,320))
    if name: cv2.putText(bg,name,(x-390,y-60),cv2.FONT_HERSHEY_SIMPLEX,1.0,(225,215,195),2,cv2.LINE_AA)
    tw=cv2.getTextSize(label,cv2.FONT_HERSHEY_SIMPLEX,sz,2)[0][0]
    cv2.putText(bg,label,(x-18-tw,y+22),cv2.FONT_HERSHEY_SIMPLEX,sz,(225,215,195),2,cv2.LINE_AA)
    cv2.rectangle(bg,(x,y-6),(x+34,y+28),(235,235,235),2)
    cv2.putText(bg,key,(x+8,y+20),cv2.FONT_HERSHEY_SIMPLEX,.8,(235,235,235),2,cv2.LINE_AA)
    return bg
def cap(img):return max(keycaps(img),key=lambda c:c[3])
def ocr_prompt(img,label,key,conf=.95):
    c=cap(img);ext=text_extent(img,c)
    return Prompt(label.replace(' [Hold]',''),key,'Hold' in label,conf,c,label,ext)
ALL=['Siphon','Fill Watering Can','Fill Compost Bucket','Collect Water','Harvest','Collect','Uproot']

class V15(unittest.TestCase):
    def learner(self,**o):
        L=Learner(tempfile.mkdtemp());L.opts=dict(o);return L
    def teach(self,L,label,key,name=None,seed=1):
        img=scene(label,key,name,seed);p=ocr_prompt(img,label,key)
        for _ in range(2):L.learn(img,[p],[(0,0,1,1,(name or '')+' '+label,.99)],20.)   # two agreeing reads
    def test_single_read_is_not_learned(self):
        L=self.learner(memory=True);img=scene('Collect','E',seed=1)
        L.learn(img,[ocr_prompt(img,'Collect','E')],[],20.);self.assertEqual(L.stats()[0],0)
    def test_memory_recalls_same_prompt_on_new_background(self):
        L=self.learner(memory=True);self.teach(L,'Harvest','F')
        out,_=L.recognize(scene('Harvest','F',seed=9,bright=160),[cap(scene('Harvest','F',seed=9,bright=160))],ALL,(),L.opts)
        self.assertEqual([(p.action,p.key,p.source) for p in out],[('Harvest','F','memory')])
    def test_memory_does_not_guess_unseen(self):
        L=self.learner(memory=True);self.teach(L,'Collect','E');self.teach(L,'Harvest','E')
        for lab,k in [('Collect','F'),('Collect Water','E'),('Harvest [Hold]','E'),('Uproot','E')]:
            img=scene(lab,k,seed=4);out,_=L.recognize(img,[cap(img)],ALL,(),L.opts)
            self.assertEqual(out,[],(lab,k))
    def test_templates_do_not_guess_unseen(self):
        L=self.learner(templates=True);self.teach(L,'Collect','E');self.teach(L,'Harvest','E')
        for lab,k in [('Collect','F'),('Collect Water','E'),('Harvest [Hold]','E')]:
            img=scene(lab,k,seed=4);out,_=L.recognize(img,[cap(img)],ALL,(),L.opts)
            self.assertEqual(out,[],(lab,k))
    def test_templates_compose_learned_parts(self):
        L=self.learner(templates=True);self.teach(L,'Harvest','E');self.teach(L,'Collect','F')
        img=scene('Harvest','F',seed=5);out,_=L.recognize(img,[cap(img)],ALL,(),L.opts)
        self.assertEqual([(p.action,p.key) for p in out],[('Harvest','F')])
    def test_memory_exclusion_uses_stored_name(self):
        L=self.learner(memory=True);self.teach(L,'Collect','E','Stone');self.teach(L,'Collect','E','Cabbage')
        img=scene('Collect','E','Stone',seed=7);out,rej=L.recognize(img,[cap(img)],ALL,('stone',),L.opts)
        self.assertEqual(out,[]);self.assertEqual(rej[0][2],'stone')
        img=scene('Collect','E','Cabbage',seed=7);out,rej=L.recognize(img,[cap(img)],ALL,('stone',),L.opts)
        self.assertEqual(len(out),1);self.assertEqual(rej,[])
    def test_disallowed_action_not_returned(self):
        L=self.learner(memory=True);self.teach(L,'Uproot','E')
        img=scene('Uproot','E',seed=3);self.assertEqual(L.recognize(img,[cap(img)],['Collect'],(),L.opts)[0],[])
    def test_limit_evicts(self):
        m=Memory();img=scene('Collect','E',seed=1);c=cap(img);per=PW*PH+KEY*KEY+64
        for i in range(12):m.add(scene('Collect','E',seed=i,bright=60+10*i),c,('Collect','E',False),f'n{i}',per*5)
        self.assertLessEqual(len(m.labels),5)
    def test_persistence_roundtrip(self):
        L=self.learner(memory=True,templates=True);self.teach(L,'Harvest','F');L.save()
        L2=Learner(L.folder);self.assertEqual(L2.stats()[:2],L.stats()[:2])
        L2.opts=dict(memory=True);img=scene('Harvest','F',seed=8);self.assertEqual(len(L2.recognize(img,[cap(img)],ALL,(),L2.opts)[0]),1)
    def test_glyph_filter(self):
        img=scene('Collect','E','Stone');caps=keycaps(img)
        self.assertTrue(has_glyph(img,cap(img)))
        empty=np.zeros((80,80,3),np.uint8);cv2.rectangle(empty,(20,20),(54,54),(240,240,240),2)
        self.assertFalse(has_glyph(empty,(20,20,35,35)))
    def test_single_scan_confirm(self):
        ev=[];c=Controller(lambda k,d:ev.append((k,d)))
        p=Prompt('Collect','E',False,.99,(0,0,30,30),'Collect')
        c.start('Auto','E',.2,.05,False,confirm=1);c.observation(p,1.);self.assertEqual(ev,[('E',True)])
        c.start('Auto','E',.2,.05,False);ev.clear();c.observation(p,1.);self.assertEqual(ev,[])
if __name__=='__main__':unittest.main()
