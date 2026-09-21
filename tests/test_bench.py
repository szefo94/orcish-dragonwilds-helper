"""2.1: automated test runs — plan, repeatable camera path, phase timing, stats, recommendations."""
import unittest, tempfile
import bench

L=('Collect Water','E',False)
def simulate(configs,behaviour,phase_s=6.,period=2.,settle=.5):
    """behaviour(cfg_id, phase, i) -> (scan_ms, label, source). Scans every 50 ms of simulated time."""
    b=bench.Benchmark(configs,phase_s=phase_s,settle_s=settle,amplitude_px=200,period_s=period);t=0.;moves=[];i=0;cpu=lambda:12.5
    while not b.done:
        moves.append(b.step(t,cpu))
        if b.measuring():
            ms,lab,src=behaviour(b.config['id'],b.phase,i);i+=1
            b.scan(ms,lab,src,t,decided=True)
        t+=.05
    return b,moves,t
class Bench(unittest.TestCase):
    def test_plan(self):
        ids=[c['id'] for c in bench.plan(['memory','fast_det'])]
        self.assertEqual(ids,['baseline','fast_det','memory','all'])
        self.assertEqual([c['id'] for c in bench.plan([])],['baseline'])
        self.assertTrue(all(not v for v in bench.plan(['gpu'])[0]['opts'].values()))
    def test_camera_path_returns_home_and_repeats(self):
        paths=[]
        for _ in range(2):
            p=bench.CameraPath(250,4);d=[p.delta(t/40) for t in range(0,161)];d.append(p.home());paths.append(d)
            self.assertEqual(sum(d),0)
        self.assertEqual(paths[0],paths[1])                                   # identical for every config
    def test_run_timing_and_camera_net_zero(self):
        cfg=bench.plan(['fast_det']);b,moves,t=simulate(cfg,lambda c,p,i:(100 if c=='baseline' else 50,L,'ocr'))
        self.assertEqual(sum(moves),0);self.assertTrue(any(moves))
        self.assertAlmostEqual(t,b.total_s(),delta=.05*len(cfg)*4+.05)   # one tick of slack per phase switch
        r=b.results();self.assertEqual(r['reference'],'Collect Water E False')
        base,fast=r['configs'][0],r['configs'][1]
        self.assertEqual(base['static']['scan_ms'],100);self.assertEqual(fast['static']['scan_ms'],50)
        self.assertEqual(fast['static']['agree_pct'],100);self.assertEqual(base['static']['cpu_pct'],12.5)
        self.assertEqual(base['static']['detect_pct'],100)
    def test_static_scans_only_in_measured_window(self):
        cfg=bench.plan([]);b,_,_=simulate(cfg,lambda c,p,i:(100,L,'ocr'),phase_s=6.,settle=.5)
        n=b.results()['configs'][0]['static']['scans'];self.assertAlmostEqual(n,120,delta=2)   # 6 s / 50 ms, settle excluded
    def test_recommend(self):
        def beh(c,p,i):
            if c=='fast_det':return (50,L,'ocr')                       # 2x faster, same result -> suggest
            if c=='rec_only':return (60,L if i%3 else None,'ocr')      # faster but misses a third -> avoid
            if c=='gpu':return (140,L,'ocr')                           # slower -> avoid
            if c=='templates':return (95,L,'template')                 # ~same -> neutral
            return (100,L,'ocr')
        b,_,_=simulate(bench.plan(['fast_det','rec_only','gpu','templates']),beh)
        rec=bench.recommend(b.results())
        self.assertEqual(rec['fast_det'][0],'suggest');self.assertEqual(rec['rec_only'][0],'avoid')
        self.assertEqual(rec['gpu'][0],'avoid');self.assertEqual(rec['templates'][0],'neutral')
        self.assertNotIn('baseline',rec);self.assertNotIn('all',rec)
    def test_wrong_label_is_avoided(self):
        other=('Collect','E',False)
        b,_,_=simulate(bench.plan(['memory']),lambda c,p,i:(20,other if c=='memory' else L,'memory'))
        self.assertEqual(bench.recommend(b.results())['memory'][0],'avoid')
    def test_abort_returns_camera(self):
        b=bench.Benchmark(bench.plan([]),phase_s=2,settle_s=.1,period_s=2);t=0;moved=0
        while not (b.phase=='camera' and b.measuring()):moved+=b.step(t);t+=.05
        for _ in range(7):moved+=b.step(t);t+=.05
        moved+=b.abort('focus lost');self.assertEqual(moved,0);self.assertTrue(b.done)
    def test_save_load(self):
        b,_,_=simulate(bench.plan([]),lambda c,p,i:(100,L,'ocr'));d=tempfile.mkdtemp()
        f=bench.save(b.results(),d);runs=bench.load_all(d);self.assertEqual(runs[0][0],f)
    def test_no_suggestions_without_prompt_in_baseline(self):
        b,_,_=simulate(bench.plan(['fast_det']),lambda c,p,i:(50 if c=='fast_det' else 100,None,None))
        self.assertFalse(bench.baseline_ok(b.results()));self.assertEqual(bench.recommend(b.results()),{})
if __name__=='__main__':unittest.main()
