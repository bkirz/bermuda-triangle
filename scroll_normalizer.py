#!/usr/bin/env python

# Written entirely by ashastral. Copied shamelessly from here:
# https://git.ashastral.com/-/snippets/4

from decimal import Decimal
import sys

import simfile
from simfile.ssc import SSCSimfile
from simfile.timing import TimingData, BeatValues, BeatValue
from simfile.timing.displaybpm import displaybpm, StaticDisplayBPM
from simfile.types import Simfile


def get_fixed_bpm(sim: Simfile) -> Decimal:
    '''
    Get a reasonable canonical BPM for the simfile.

    If a DISPLAYBPM is set, its maximum bpm will be used.
    Otherwise, the song's maximum BPM will be used.
    '''
    return displaybpm(sim).max


def scroll_value(fixed_bpm: Decimal, current_bpm: Decimal):
    '''Get the new scroll value at the current BPM.'''
    return (fixed_bpm / current_bpm).quantize(Decimal('1.000'))


def fixedscroll(sim: SSCSimfile):
    '''Set the simfile's scrolls to counteract any BPM changes.'''
    timing = TimingData(sim)
    fixed_bpm = get_fixed_bpm(sim)
    sim.scrolls = str(BeatValues([
        BeatValue(beat=bpm.beat, value=scroll_value(fixed_bpm, bpm.value))
        for bpm in timing.bpms
    ]))


def main(input_filename, output_filename=None):
    '''
    Run :func:`fixedscroll` on the input file.
    
    If no output file is specified, writes back to the input file.
    '''
    with simfile.mutate(
        input_filename,
        output_filename,
        backup_filename=f'{input_filename}~'
    ) as sim:
        assert isinstance(sim, SSCSimfile)
        fixedscroll(sim)


if __name__ == '__main__':
    main(*sys.argv)