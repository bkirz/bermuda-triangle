R"""
Add a short fake region on every isolated mine
to prevent them from being hit during gameplay.

This script only works on SSC files.

Usage examples:

    # Preview changes & detect any errors
    python make_mines_fake.py "C:\StepMania\Songs\My Pack\My Song" --dry-run

    # Preview changes with errors & warnings suppressed
    python make_mines_fake.py "C:\StepMania\Songs\My Pack\My Song" --dry-run --allow-simultaneous --allow-split-timing --ignore-sm

    # Commit changes with only warnings suppressed
    python make_mines_fake.py "C:\StepMania\Songs\My Pack\My Song" --ignore-sm
"""
import argparse
import bisect
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
import heapq
import os
import sys
from typing import Iterator, List, NamedTuple, Optional, Union

import simfile
import simfile.dir
from simfile.notes import NoteData, NoteType
from simfile.notes.group import group_notes, SameBeatNotes
from simfile.timing import Beat, BeatValue, BeatValues


####################
# Script arguments #
####################


class MakeMinesFakeArgs:
    """Stores the command-line arguments for this script."""

    simfile: str
    dry_run: bool
    allow_split_timing: bool
    allow_simultaneous: bool
    ignore_sm: bool


def argparser():
    """Get an ArgumentParser instance for this command-line script."""
    parser = argparse.ArgumentParser()
    parser.add_argument("simfile", type=str, help="path to the simfile to modify")
    parser.add_argument(
        "-d",
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        help="preview changes without writing the file",
    )
    parser.add_argument(
        "--allow-split-timing",
        action=argparse.BooleanOptionalAction,
        help="if necessary, create split timing for charts to avoid interfering with other charts",
    )
    parser.add_argument(
        "--allow-simultaneous",
        action=argparse.BooleanOptionalAction,
        help="leave mines that occur on the same beat as notes alone",
    )
    parser.add_argument(
        "--ignore-sm",
        action=argparse.BooleanOptionalAction,
        help="do not warn when an SM file is present alongside the SSC file",
    )
    return parser


#####################
# Utility functions #
#####################


def whichchart(
    ssc: simfile.ssc.SSCSimfile, chart: Union[int, simfile.ssc.SSCChart]
) -> str:
    """
    Identify the chart by its difficulty,
    as well as its stepstype if multiple are present in the simfile.
    Intended for human-readable output.
    """
    if isinstance(chart, int):
        chartobj_ = ssc.charts[chart]
        chartobj: simfile.ssc.SSCChart = chartobj_  # typing workaround
    else:
        chartobj = chart

    stepstypes = set(ch.stepstype for ch in ssc.charts)
    if len(stepstypes) > 1:
        return f"{chartobj.stepstype} {chartobj.difficulty}"
    else:
        return chartobj.difficulty or ""


def whichtarget(
    ssc: simfile.ssc.SSCSimfile,
    target: Union[simfile.ssc.SSCSimfile, simfile.ssc.SSCChart],
) -> str:
    """
    Identify the target as a chart (see :func:`whichchart`) or simfile.
    Intended for human-readable output.

    Returns a string starting with "the ".
    """
    if isinstance(target, simfile.ssc.SSCChart):
        return f"the {whichchart(ssc, target)} chart"
    else:
        return "the simfile"


def hastiming(chart: simfile.ssc.SSCChart) -> bool:
    """
    Detect whether the chart has its own timing data.
    """
    return chart.bpms is not None


def splittiming(ssc: simfile.ssc.SSCSimfile, chart: simfile.ssc.SSCChart) -> None:
    """
    Copy timing data from the SSC simfile to its chart.
    """
    for td in (
        "STOPS",
        "DELAYS",
        "BPMS",
        "OFFSET",
        "WARPS",
        "LABELS",
        "TIMESIGNATURES",
        "TICKCOUNTS",
        "COMBOS",
        "SPEEDS",
        "SCROLLS",
        "FAKES",
    ):
        if td in ssc:
            chart[td] = ssc[td]


################
# Script logic #
################


class BeatChartIndex(NamedTuple):
    beat: Beat
    chart_index: int


class SameBeatMineAndNote(NamedTuple):
    beat: Beat
    mine_chart_index: int
    note_chart_index: int


@dataclass
class NotesAndMines:
    """
    Note & mine data across all charts of a simfile.
    """

    note_positions: List[BeatChartIndex] = field(default_factory=list)
    """
    All of the non-fake, non-mine note object positions in each chart.
    Sorted first by beat, then by chart index.
    """

    mine_positions: List[BeatChartIndex] = field(default_factory=list)
    """
    All of the mine note object positions in each chart.
    Sorted first by beat, then chart index.
    """

    must_allow_simultaneous: List[SameBeatMineAndNote] = field(default_factory=list)
    """All of the same-beat mine & note pairs within the same chart."""

    must_allow_split_timing: List[SameBeatMineAndNote] = field(default_factory=list)
    """All of the same-beat mine & note pairs across different charts."""


class SameBeatMineAndNoteError(Exception):
    """
    Raised if a mine & note occur on the same beat
    and such an occurrence isn't explicitly allowed by the input arguments.
    Stringifies to a multi-line, human-readable error message.
    """

    def __init__(
        self,
        ssc: simfile.ssc.SSCSimfile,
        must_allow_simultaneous: List[SameBeatMineAndNote],
        must_allow_split_timing: List[SameBeatMineAndNote],
    ):
        self.ssc = ssc
        self.must_allow_simultaneous = must_allow_simultaneous
        self.must_allow_split_timing = must_allow_split_timing

    def _stringify_simultaneous(self, s: SameBeatMineAndNote):
        if s.mine_chart_index == s.note_chart_index:
            return f"b{s.beat} in {whichchart(self.ssc, s.mine_chart_index)}"
        else:
            return f"b{s.beat} in {whichchart(self.ssc, s.mine_chart_index)} and {whichchart(self.ssc, s.note_chart_index)}"

    def _stringify_simultaneous_list(self, sl: List[SameBeatMineAndNote]):
        return "".join(f"    {self._stringify_simultaneous(s)}\n" for s in sl)

    def __str__(self):
        return (
            f"ERROR: There are simultaneous mines and notes in your file;\n"
            "you will have to either update the chart or opt into certain behavior\n"
            "in order to remedy this error.\n"
            + (
                "\n"
                "Simultaneous mine & note in the same chart (ignore with 'Allow simultaneous note & mine'):\n"
                f"{self._stringify_simultaneous_list(self.must_allow_simultaneous)}"
                "Ignoring these occurrences will leave the mines on these beats hittable,\n"
                "which may surprise players. Consider relocating these mines instead.\n"
                if self.must_allow_simultaneous
                else ""
            )
            + (
                "\n"
                "Simultaneous mine & note in different charts (fix with 'Allow split timing'):\n"
                f"{self._stringify_simultaneous_list(self.must_allow_split_timing)}"
                "Note that split timing makes it easy to mess up the timing data if you are\n"
                "still making changes to the chart. Use this feature with caution.\n"
                if self.must_allow_split_timing
                else ""
            )
        )


def find_chart_with_existing_item(
    positions: List[BeatChartIndex],
    position: BeatChartIndex,
) -> Optional[int]:
    """
    If `positions` has an item on the same beat as `position`,
    returns the chart index of the found item.
    """
    if not positions:
        return None
    index = bisect.bisect_left(positions, position.beat, key=lambda pos: pos.beat)
    if index == len(positions):
        return None
    item = positions[index]
    if item.beat == position.beat:
        return item.chart_index


def append_same_beat_items(
    nm: NotesAndMines,
    chart_positions: List[BeatChartIndex],
    position: BeatChartIndex,
    *,
    position_is_mine: bool,
) -> None:
    """
    If the given position occurs in the other type of items (between notes and mines),
    append a SameBeatMineAndNote to the appropriate NotesAndMines `must_allow` list.
    """
    items_from_other_charts = (
        nm.note_positions if position_is_mine else nm.mine_positions
    )

    # Look for a note on the same beat in a previously indexed chart
    if (
        other_chart := find_chart_with_existing_item(items_from_other_charts, position)
    ) is not None:
        mine_chart_index = position.chart_index if position_is_mine else other_chart
        note_chart_index = other_chart if position_is_mine else position.chart_index
        nm.must_allow_split_timing.append(
            SameBeatMineAndNote(
                beat=position.beat,
                mine_chart_index=mine_chart_index,
                note_chart_index=note_chart_index,
            )
        )

    # Look for a note on the same beat in this chart
    if find_chart_with_existing_item(chart_positions, position) is not None:
        nm.must_allow_simultaneous.append(
            SameBeatMineAndNote(
                beat=position.beat,
                mine_chart_index=position.chart_index,
                note_chart_index=position.chart_index,
            )
        )


def get_notes_and_mines(ssc: simfile.ssc.SSCSimfile) -> NotesAndMines:
    """
    Populate & return a NotesAndMines instance for the simfile.
    """
    output = NotesAndMines()

    for c, chart in enumerate(ssc.charts):
        chart_note_positions: List[BeatChartIndex] = []
        """All of the non-fake, non-mine note object positions in this chart. Sorted by beat."""

        chart_mine_positions: List[BeatChartIndex] = []
        """All of the mine note object positions in this chart. Sorted by beat."""

        nd = NoteData(chart)
        for note in nd:
            position = BeatChartIndex(beat=note.beat, chart_index=c)
            match note.note_type:
                case NoteType.MINE:
                    append_same_beat_items(
                        output, chart_note_positions, position, position_is_mine=True
                    )
                    chart_mine_positions.append(position)

                case NoteType.FAKE | NoteType.TAIL:
                    pass

                case _:  # Any hittable or scoreable "note"
                    append_same_beat_items(
                        output, chart_mine_positions, position, position_is_mine=False
                    )
                    chart_note_positions.append(position)

        output.note_positions = list(
            heapq.merge(output.note_positions, chart_note_positions)
        )
        output.mine_positions = list(
            heapq.merge(output.mine_positions, chart_mine_positions)
        )

    return output


def maybe_raise_simultaneous_error(
    ssc: simfile.ssc.SSCSimfile,
    args: MakeMinesFakeArgs,
    nm: NotesAndMines,
) -> None:
    """
    Raise :class:`SameBeatMineAndNoteError`
    only if the script arguments don't allow for same-beat mine & note pairs
    that were found in the simfile.
    """
    simultaneous = [] if args.allow_simultaneous else nm.must_allow_simultaneous
    split_timing = [] if args.allow_split_timing else nm.must_allow_split_timing

    if simultaneous or split_timing:
        raise SameBeatMineAndNoteError(
            ssc,
            must_allow_simultaneous=simultaneous,
            must_allow_split_timing=split_timing,
        )


def charts_with_mines(
    ssc: simfile.ssc.SSCSimfile, nm: NotesAndMines
) -> Iterator[simfile.ssc.SSCChart]:
    """
    Yield only the charts that have mines.
    Sorted by chart index.
    """
    chart_indexes = set(mine_pos.chart_index for mine_pos in nm.mine_positions)
    for chart_index in sorted(chart_indexes):
        yield ssc.charts[chart_index]


def beat_is_already_fake(beat: Beat, fakes: BeatValues) -> bool:
    for fake_ in fakes:
        fake: BeatValue = fake_  # typing workaround

        # Convert the decimal value to string first
        # to force Beat() to quantize it to a 192nd
        fake_end_beat = fake.beat + Beat(str(fake.value))

        if fake.beat <= beat < fake_end_beat:
            return True

        # Stop checking fake segments past the current mine's beat
        # Assumption: fake region start & end beats are strictly increasing
        if fake.beat > beat:
            return False

    # Any existing fakes are before this mine
    return False


@dataclass
class Action:
    text: str
    noop: bool = False

    def __str__(self):
        return ("[no-op] " if self.noop else "") + self.text


def make_mines_fake(
    ssc: simfile.ssc.SSCSimfile, args: MakeMinesFakeArgs
) -> List[Action]:
    """
    Add a short fake segment on each mine in each chart in the simfile,
    updating the in-memory simfile object.

    Returns a list of actions (human-readable strings)
    that were taken on the simfile.

    Raises :class:`SameBeatMineAndNoteError`
    if a mine & note are found on the same beat
    and the arguments don't explicitly allow it.
    """
    actions: List[Action] = []
    """
    Actions that have been taken on the simfile.
    
    Care should be taken to always append to this list
    when mutating the simfile or any of its charts
    because :func:`main` skips saving the file
    if the actions list comes back empty.
    """

    nm = get_notes_and_mines(ssc)
    maybe_raise_simultaneous_error(ssc, args, nm)

    skipped_mines = 0

    for chart in charts_with_mines(ssc, nm):
        if hastiming(chart):
            fakes_target = chart
        elif len(nm.must_allow_split_timing) > 0:
            copy_action = f"copy timing data from the simfile to the {whichchart(ssc, chart)} chart"
            actions.append(Action(copy_action))
            splittiming(ssc, chart)
            fakes_target = chart
        else:
            fakes_target = ssc

        fakes = BeatValues.from_str(fakes_target.fakes or "")

        for note_group in group_notes(
            NoteData(chart),
            same_beat_notes=SameBeatNotes.JOIN_ALL,
            join_heads_to_tails=True,
        ):
            if any(note.note_type == NoteType.MINE for note in note_group):
                beat = note_group[0].beat

                if not all(note.note_type == NoteType.MINE for note in note_group):
                    # This case should've been caught already
                    assert args.allow_simultaneous
                    continue

                if beat_is_already_fake(beat, fakes):
                    skipped_mines += 1
                    continue

                add_fake_action = f"add a short fake region on b{beat} to {whichtarget(ssc, fakes_target)}"
                actions.append(Action(add_fake_action))
                bisect.insort(
                    fakes,
                    BeatValue(beat=beat, value=Decimal(str(Beat.tick()))),
                    key=lambda bv: bv.beat,
                )

        fakes_target.fakes = str(fakes)

    if skipped_mines:
        actions.append(Action(f"skipped {skipped_mines} already-fake mines", noop=True))

    return actions


def maybe_print_sm_present_warning(ssc: simfile.ssc.SSCSimfile) -> bool:
    """
    If the SSC simfile has split timing,
    print a warning to stdout.
    """
    ssc_has_split_timing = any(hastiming(chart) for chart in ssc.charts)
    if ssc_has_split_timing:
        print(
            "WARNING: there is an SM file in this directory, but the SSC has split timing.\n"
            "The StepMania editor will not save an SM file in this case,\n"
            "and the two files may become out of sync.\n"
            "Delete the SM file or pass --ignore-sm to suppress this warning.\n"
        )
        return True
    return False


def main(argv) -> int:
    """
    Run the script & return an exit code (0 for success, nonzero for error).
    """
    error = False

    # Parse command-line arguments
    args = argparser().parse_args(argv[1:], namespace=MakeMinesFakeArgs())

    sm_present = False
    printed_sm_present_warning = False

    if os.path.isdir(args.simfile):
        sd = simfile.dir.SimfileDirectory(args.simfile)
        if sd.ssc_path:
            args.simfile = sd.ssc_path
        else:
            raise ValueError("simfile directory has no SSC file")

        if sd.sm_path and not args.ignore_sm:
            sm_present = True

    input_filename = args.simfile
    backup_filename = input_filename + "~"

    with simfile.mutate(input_filename, backup_filename=backup_filename) as ssc:
        if not isinstance(ssc, simfile.ssc.SSCSimfile):
            raise TypeError("fakes require an SSC file")

        # If the SSC already has split timing, print the warning before any errors
        if sm_present:
            printed_sm_present_warning = maybe_print_sm_present_warning(ssc)

        try:
            actions = make_mines_fake(ssc, args)
        except SameBeatMineAndNoteError as e:
            print(str(e))
            actions = []
            error = True

        # If this run gave the SSC split timing, print the warning now
        if sm_present and not printed_sm_present_warning:
            printed_sm_present_warning = maybe_print_sm_present_warning(ssc)

        if any(not a.noop for a in actions):
            print("Actions taken:")
            print("".join(f"    {a}\n" for a in actions))
        else:
            print(f"No actions taken{':' if actions else ''}")
            print("".join(f"    {a}\n" for a in actions))
            raise simfile.CancelMutation

        if args.dry_run:
            print("Not writing changes for dry run")
            raise simfile.CancelMutation
        else:
            print(
                f"Writing changes to {input_filename} & backing up original file to {backup_filename}"
            )

    return 1 if error else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
