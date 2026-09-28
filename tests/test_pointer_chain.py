import ctypes, os, sys, unittest

from pointer_chain import format_ops, is_pointer_expr, parse_pointer_expr, resolve_ops
from scout_lab import parse_watch, parse_candidate

GAME="RSDragonwilds-WinGDK-Shipping.exe"


class PointerChainParseTests(unittest.TestCase):
    def test_module_chain_with_hyphenated_name(self):
        ops=parse_pointer_expr(f"[[{GAME}+0x4A1230]+0x10]+0x88")
        self.assertEqual(ops,[("module",GAME.lower()),("add",0x4A1230),("deref",),("add",0x10),("deref",),("add",0x88)])

    def test_quoted_module_absolute_base_and_negative_offset(self):
        self.assertEqual(parse_pointer_expr('["Game.dll"+0x20]-0x8'),[("module","game.dll"),("add",0x20),("deref",),("add",-8)])
        self.assertEqual(parse_pointer_expr("[0x7FF600001000]"),[("abs",0x7FF600001000),("deref",)])

    def test_format_round_trips(self):
        for text in (f"[[{GAME.lower()}+0x4A1230]+0x10]+0x88","[0x1000]-0x8","[[[0x10]+0x1]+0x2]"):
            with self.subTest(text=text):self.assertEqual(format_ops(parse_pointer_expr(text)),text)

    def test_bare_hex_offset_is_rejected_not_read_as_decimal(self):
        with self.assertRaisesRegex(ValueError,"0x10"):parse_pointer_expr(f"[{GAME}+0x4A1230]+10")
        with self.assertRaisesRegex(ValueError,"0x4A1230"):parse_pointer_expr(f"[{GAME}+4A1230]")

    def test_malformed_expressions_are_rejected(self):
        for text in ("[game.exe+0x10","game.exe+0x10]","[game+0x10]","[]","[game.exe+]","[game.exe+0x1]]","[0x0]",
                     "["*14+"0x10"+"]"*14):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):parse_pointer_expr(text)

    def test_is_pointer_expr(self):
        self.assertTrue(is_pointer_expr("[a.exe+0x1]"));self.assertFalse(is_pointer_expr("a.exe+0x1"))


class PointerChainResolveTests(unittest.TestCase):
    MEMORY={0x1000+0x4A1230:0x20000,0x20000+0x10:0x30000}

    def resolve(self,text,memory=None,modules=None):
        memory=self.MEMORY if memory is None else memory
        modules={"game.exe":0x1000} if modules is None else modules
        return resolve_ops(parse_pointer_expr(text),modules.get,memory.get)

    def test_resolves_final_address_and_trail(self):
        r=self.resolve("[[game.exe+0x4A1230]+0x10]+0x88")
        self.assertTrue(r["ok"]);self.assertEqual(r["address"],0x30088)
        self.assertEqual(r["trail"],[{"at":0x4A2230,"pointer":0x20000},{"at":0x20010,"pointer":0x30000}])

    def test_reports_failing_level(self):
        r=self.resolve("[[game.exe+0x4A1230]+0x18]+0x88")
        self.assertEqual((r["ok"],r["error"],r["level"]),(False,"pointer_read_failed",2))
        r=self.resolve("[[game.exe+0x4A1230]+0x10]+0x8",memory={0x4A2230:0x20000,0x20010:0})
        self.assertEqual((r["error"],r["level"]),("null_pointer",2))
        self.assertEqual(self.resolve("[other.dll+0x1]")["error"],"module_not_found")


class PointerWatchTests(unittest.TestCase):
    def test_watch_and_candidate_accept_pointer_chains(self):
        w=parse_watch(f"[[{GAME}+0x4A1230]+0x10]+0x88:i32")
        self.assertEqual(w["type"],"i32");self.assertEqual(len([o for o in w["chain"] if o[0]=="deref"]),2)
        self.assertIsNone(w["module"]);self.assertIsNone(w["address"])
        c=parse_candidate({"name":"phase","domain":"fishing","role":"phase","spec":f"[{GAME}+0x10]+0x4:u8"})
        self.assertEqual(c["chain"][0],("module",GAME.lower()))

    def test_flat_watches_are_unchanged(self):
        w=parse_watch("Game.exe+0x10:u32")
        self.assertEqual((w["module"],w["offset"],w.get("chain")),("game.exe",0x10,None))


@unittest.skipUnless(sys.platform=="win32","ReadProcessMemory is Windows-only")
class ReadOnlyMemoryPointerTests(unittest.TestCase):
    def test_reads_value_through_chain_in_own_process(self):
        from scout_lab import ReadOnlyMemory
        value=ctypes.c_int32(-1234)
        # [base] -> level1; [level1+0x10] (slot 2) -> value-0x8; +0x8 -> value
        level1=(ctypes.c_uint64*4)(0,0,ctypes.addressof(value)-0x8,0)
        base=ctypes.c_uint64(ctypes.addressof(level1))
        spec=f"[[0x{ctypes.addressof(base):X}]+0x10]+0x8:i32"
        m=ReadOnlyMemory(os.getpid())
        try:
            flat=m.read(parse_watch(f"0x{ctypes.addressof(value):X}:i32"))
            self.assertEqual((flat["ok"],flat["value"]),(True,-1234))
            r=m.read(parse_watch(spec))
            self.assertEqual((r["ok"],r["value"],r["address"]),(True,-1234,ctypes.addressof(value)))
            level1[2]=0
            broken=m.read(parse_watch(spec))
            self.assertEqual((broken["ok"],broken["error"]),(False,"null_pointer"))
            self.assertEqual(len(broken["chain"]),2)
        finally:m.close()


if __name__=="__main__":unittest.main()
