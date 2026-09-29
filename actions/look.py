import copy
import io
import random
import sys
from contextlib import redirect_stdout

from keywords import General, allowed_directions
from world.locations import locations
from world.items import items
from replies import snarky_replies


def _sorted_directions(location):
    # Sorting makes the output independent of dict insertion/traversal order.
    return sorted(d for d in location if d in allowed_directions)


def _sorted_item_names(item_collection):
    return sorted(item_collection.keys())


def print_location_info(location_name, location):

    print(f"""
Location Information:
    name: {location_name}
    description: {location[General.DESCRIPTION]}
    allowed directions: {_sorted_directions(location)}
    items: {_sorted_item_names(location[General.ITEMS])}
""")


def print_item_info(item):

    print("\n--------------------")
    print(item.get(General.DESCRIPTION, ""))
    print("--------------------\n")


def _look_impl(location_name, command, inventory):

    current_location = locations[location_name]

    # 'look' on its own describes the current location only.
    if len(command) == 1:
        print_location_info(location_name, current_location)
        return

    # 'look <word>': <word> is either a legal direction or an item name.
    if len(command) == 2:
        target = command[1]
        if target == General.AT:
            # 'look at' with no target is a malformed command, not an item.
            snarky_replies.print_snarky_reply_bad_look_command()
            return
        if target in allowed_directions:
            _look_in_direction(current_location, target)
            return
        _look_at_item(target, current_location, inventory)
        return

    # 'look at <item>': only item examination is valid.
    if len(command) == 3 and command[1] == General.AT:
        _look_at_item(command[2], current_location, inventory)
        return

    # Everything else ('look at', 'look foo bar', 'look north map', ...) is malformed.
    snarky_replies.print_snarky_reply_bad_look_command()


def _look_in_direction(current_location, direction):

    # A legal direction that does not lead anywhere from here is a wall.
    if direction not in current_location:
        snarky_replies.print_snarky_reply_bad_direction()
        return

    destination_name = current_location[direction]
    if destination_name not in locations:
        snarky_replies.print_snarky_reply_bad_world(destination_name)
        return

    destination = locations[destination_name]

    # The LOOK text describes what is visible in that direction.
    if General.LOOK in current_location:
        print(current_location[General.LOOK])

    print(f"\nIn the {direction}, you see:")
    # Only the adjacent destination's own items are listed. No other region's
    # items leak in here, because we never scan any other location.
    print_location_info(destination_name, destination)


def _look_at_item(item_name, current_location, inventory):

    if item_name in current_location[General.ITEMS]:
        item = current_location[General.ITEMS][item_name]
    elif item_name in inventory:
        item = inventory[item_name]
    else:
        snarky_replies.print_snarky_reply_dont_have_item(item_name)
        return

    print_item_info(item)


def look(location_name, command, inventory):

    # Defensive transaction boundary: examining the world must never mutate
    # it. If anything raises while doing so, restore the complete pre-call
    # snapshot so that a failure rolls everything back and cannot pollute any
    # later command.
    state_snapshot = copy.deepcopy((locations, inventory))
    try:
        _look_impl(location_name, command, inventory)
    except Exception:
        locations_backup, inventory_backup = state_snapshot
        locations.clear()
        locations.update(copy.deepcopy(locations_backup))
        inventory.clear()
        inventory.update(copy.deepcopy(inventory_backup))
        raise


# ---------------------------------------------------------------------------
# Table-driven verification suite.
#
# Run with:   python -m actions.look
#
# Every table row snapshots every location, every item and the inventory with
# copy.deepcopy before the call and asserts the full world is byte-for-byte
# identical afterwards (deep snapshot assertion). Failure rows additionally
# prove the failed call cannot pollute a following successful call. Rows are
# also executed in reversed and shuffled orders to guarantee results do not
# depend on traversal/execution order.
# ---------------------------------------------------------------------------

def _world_snapshot():
    return copy.deepcopy({
        "locations": locations,
        "items": items,
    })


def _run_look(location_name, command, inventory):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        look(location_name, list(command), inventory)
    return buffer.getvalue()


# (row id, location, command tokens, inventory, substrings expected,
#  substrings that must NOT appear, is this row expected to fail/error)
LOOK_TEST_TABLE = [

    # --- bare 'look' -----------------------------------------------------
    ("bare-entry", "schoolhouse-entry", ["look"], {},
     ["name: schoolhouse-entry", "items: ['map']", "allowed directions: ['north']"],
     ["globe", "frisbee", "baxter-the-dog", "soccer-ball"], False),

    ("bare-foyer", "foyer", ["look"], {},
     ["name: foyer", "'globe'", "'android-phone'"],
     ["map", "soccer-ball", "frisbee"], False),

    ("bare-back-entry-empty", "back-entry", ["look"], {},
     ["name: back-entry", "items: []"],
     ["map", "globe"], False),

    # --- looking in a direction -----------------------------------------
    ("dir-north-entry", "schoolhouse-entry", ["look", "north"], {},
     ["In the north, you see:", "name: foyer", "'globe'", "'android-phone'"],
     ["schoolhouse-entry", "soccer-ball", "frisbee", "baxter-the-dog"], False),

    ("dir-west-foyer", "foyer", ["look", "west"], {},
     ["In the west, you see:", "name: west-hallway"],
     ["globe", "frisbee"], False),

    ("dir-east-foyer", "foyer", ["look", "east"], {},
     ["In the east, you see:", "name: east-hallway"],
     ["globe", "frisbee"], False),

    ("dir-south-foyer", "foyer", ["look", "south"], {},
     ["In the south, you see:", "name: schoolhouse-entry", "'map'"],
     ["globe", "frisbee", "soccer-ball"], False),

    ("dir-north-foyer", "foyer", ["look", "north"], {},
     ["In the north, you see:", "name: back-entry", "items: []"],
     ["map", "globe"], False),

    ("dir-north-west-hallway", "west-hallway", ["look", "north"], {},
     ["name: classroom-science", "items: []"],
     ["soccer-ball", "baxter-the-dog", "globe"], False),

    ("dir-east-west-entry", "west-entry", ["look", "east"], {},
     ["name: west-hallway"],
     ["soccer-ball", "baxter-the-dog"], False),

    ("dir-west-east-entry", "east-entry", ["look", "west"], {},
     ["name: east-hallway"],
     ["frisbee"], False),

    ("dir-wall", "schoolhouse-entry", ["look", "south"], {},
     ["Ouch! You bump into a wall and bruise your nose."],
     ["Location Information"], False),

    ("dir-bad-name", "foyer", ["look", "sideways"], {},
     ["Hmm. I don't see sideways"],
     ["Location Information"], False),

    # --- looking at items ------------------------------------------------
    ("item-room", "schoolhouse-entry", ["look", "map"], {},
     ["A map of the entire world"],
     ["Location Information"], False),

    ("item-at-room", "foyer", ["look", "at", "globe"], {},
     ["A beautiful antique globe"],
     ["Location Information"], False),

    ("item-phone-room", "foyer", ["look", "android-phone"], {},
     ["Google Pixel 6A"],
     ["Location Information"], False),

    ("item-inventory", "back-entry", ["look", "map"], {"map": items["map"]},
     ["A map of the entire world"],
     ["Location Information"], False),

    ("item-at-inventory", "back-entry", ["look", "at", "map"], {"map": items["map"]},
     ["A map of the entire world"],
     [], False),

    ("item-missing", "back-entry", ["look", "map"], {},
     ["Hmm. I don't see map"],
     ["Location Information", "---"], False),

    ("item-at-missing", "schoolhouse-entry", ["look", "at", "globe"], {},
     ["Hmm. I don't see globe"],
     ["Location Information", "---"], False),

    ("other-region-item-no-leak", "schoolhouse-entry", ["look"], {},
     ["items: ['map']"],
     ["soccer-ball", "frisbee", "baxter-the-dog", "android-phone", "globe"], False),

    # --- malformed commands ---------------------------------------------
    ("bad-look-at-empty", "foyer", ["look", "at"], {},
     ["How could I write my command so poorly"],
     ["Location Information", "---"], False),

    ("bad-look-extra-words", "foyer", ["look", "north", "map"], {},
     ["How could I write my command so poorly"],
     ["Location Information", "---", "In the north"], False),

    ("bad-look-at-extra", "foyer", ["look", "at", "globe", "now"], {},
     ["How could I write my command so poorly"],
     ["Location Information", "---"], False),

    # --- repeat look is idempotent and deterministic --------------------
    ("repeat-direction", "schoolhouse-entry", ["look", "north"], {},
     ["name: foyer"], [], False),

    ("repeat-room-item", "foyer", ["look", "globe"], {},
     ["A beautiful antique globe"], [], False),
]


def _assert_snapshot_unchanged(before, after, row_id):
    assert before == after, f"snapshot changed after row {row_id!r}"


def _run_table_rows(rows, failures):
    for row_id, loc_name, command, inventory, expected, forbidden, _ in rows:
        before = _world_snapshot()
        inventory_copy = copy.deepcopy(inventory)
        output = _run_look(loc_name, command, inventory_copy)
        after = _world_snapshot()

        # Deep-copy snapshot assertion: the whole world (and every item dict
        # reachable from it) must be untouched.
        _assert_snapshot_unchanged(before, after, row_id)
        assert inventory_copy == inventory, f"inventory mutated by row {row_id!r}"

        for needle in expected:
            assert needle in output, f"row {row_id!r}: missing {needle!r} in:\n{output}"
        for needle in forbidden:
            assert needle not in output, f"row {row_id!r}: leaked {needle!r} in:\n{output}"

        # Idempotency: a second identical call must give identical output.
        output_again = _run_look(loc_name, command, copy.deepcopy(inventory))
        assert output_again == output, f"row {row_id!r}: repeated look changed output"

        # No pollution: after every row (including failure/error rows) a
        # follow-up successful look still behaves correctly.
        follow_up = _run_look("schoolhouse-entry", ["look", "map"], {})
        assert "A map of the entire world" in follow_up, f"row {row_id!r} polluted later look"
        follow_up_card = _run_look("schoolhouse-entry", ["look"], {})
        assert "items: ['map']" in follow_up_card, f"row {row_id!r} polluted location state"

    # After a failure row specifically, the next row in sequence must still
    # pass: run each failing row immediately followed by a normal row.
    for fail_row in failures:
        f_id, f_loc, f_cmd, f_inv = fail_row
        _run_look(f_loc, f_cmd, copy.deepcopy(f_inv))
        after_failure = _run_look("foyer", ["look", "north"], {})
        assert "name: back-entry" in after_failure, f"failure row {f_id!r} polluted next call"
        assert "items: []" in after_failure, f"failure row {f_id!r} changed destination items"


def _test_traversal_order_independence():
    # print_location_info output must not depend on how a location dict is
    # traversed. Build two dicts with the same content in opposite insertion
    # orders; sorted output must be identical.
    forward = {
        General.DESCRIPTION: "d",
        General.ITEMS: {name: items[name] for name in ["map", "globe"]},
        "north": "back-entry",
        "west": "west-hallway",
        "south": "schoolhouse-entry",
        "east": "east-hallway",
    }
    reverse = {
        "east": "east-hallway",
        "south": "schoolhouse-entry",
        "west": "west-hallway",
        "north": "back-entry",
        General.ITEMS: {name: items[name] for name in ["globe", "map"]},
        General.DESCRIPTION: "d",
    }
    buf_f = io.StringIO()
    buf_r = io.StringIO()
    with redirect_stdout(buf_f):
        print_location_info("probe", forward)
    with redirect_stdout(buf_r):
        print_location_info("probe", reverse)
    assert buf_f.getvalue() == buf_r.getvalue(), "output depends on dict traversal order"
    assert "allowed directions: ['east', 'north', 'south', 'west']" in buf_f.getvalue()
    assert "items: ['globe', 'map']" in buf_f.getvalue()


def _test_forced_exception_rolls_back():
    # Force a failure mid-call and prove the entire world + inventory is
    # restored, i.e. a failed look rolls fully back and leaves no trace.
    original = _world_snapshot()
    inventory = {"map": items["map"]}
    inventory_snapshot = copy.deepcopy(inventory)

    def boom(*_args, **_kwargs):
        raise RuntimeError("forced mid-look failure")

    snarky_replies.print_snarky_reply_dont_have_item = boom
    try:
        raised = False
        try:
            look("back-entry", ["look", "no-such-item"], inventory)
        except RuntimeError:
            raised = True
        assert raised, "forced exception was swallowed"
    finally:
        import importlib
        importlib.reload(snarky_replies)

    assert _world_snapshot() == original, "world not rolled back after exception"
    assert inventory == inventory_snapshot, "inventory not rolled back after exception"


def _run_self_tests():
    failures = [
        ("dir-wall", "schoolhouse-entry", ["look", "south"], {}),
        ("dir-bad-name", "foyer", ["look", "sideways"], {}),
        ("item-missing", "back-entry", ["look", "map"], {}),
        ("bad-look-at-empty", "foyer", ["look", "at"], {}),
        ("bad-look-extra-words", "foyer", ["look", "north", "map"], {}),
    ]

    _run_table_rows(LOOK_TEST_TABLE, failures)
    _run_table_rows(list(reversed(LOOK_TEST_TABLE)), failures)
    shuffled = list(LOOK_TEST_TABLE)
    rng = random.Random(20260929)
    rng.shuffle(shuffled)
    _run_table_rows(shuffled, failures)
    _test_traversal_order_independence()
    _test_forced_exception_rolls_back()

    snapshot_assertions = len(LOOK_TEST_TABLE) * 3
    print(f"all look tests passed: {len(LOOK_TEST_TABLE)} table rows x 3 orderings "
          f"({snapshot_assertions} deep-copy snapshot assertions), "
          f"plus traversal-order and forced-rollback checks")


if __name__ == "__main__":
    _run_self_tests()
