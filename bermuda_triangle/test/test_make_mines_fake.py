import unittest
import simfile
from simfile.timing import Beat, BeatValue, BeatValues
from bermuda_triangle import make_mines_fake

class MakeMinesFakeTest(unittest.TestCase):
    def _assert_chart_generates_fakes(self, notes: str, expected_beats: list[Beat]):
        ssc = simfile.SSCSimfile.blank()
        chart = simfile.ssc.SSCChart.blank()
        chart.notes = notes
        ssc.charts.append(chart)

        args = make_mines_fake.MakeMinesFakeArgs() 
        args.allow_simultaneous = False
        args.allow_split_timing = False
        make_mines_fake.make_mines_fake(ssc, args)
        fake_beats = [fake.beat for fake in BeatValues.from_str(ssc.fakes)]

        self.assertEqual(expected_beats, fake_beats)


    def test_fake_one_mine(self):
        self._assert_chart_generates_fakes("M000", [Beat(0)])
    
    def test_mine_aligned_with_tail(self):
        self._assert_chart_generates_fakes(
            """ 2000
                0000
                300M
                0000""", 
            [Beat(2)])