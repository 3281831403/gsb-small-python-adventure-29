if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import copy
from contextlib import redirect_stdout
import io

from keywords import General, Item, allowed_directions
from world.locations import locations
from replies import snarky_replies
from world.items import items


def print_location_info(location_name, location):

    print(f"""
Location Information:
    name: {location_name}
    description: {location[General.DESCRIPTION]}
    allowed directions: {sorted(d for d in location.keys() if d in allowed_directions)}
    items: {sorted(location[General.ITEMS].keys())}
""")


def print_item_info(item_name, item):

    print("\n--------------------")
    print(item.get(General.DESCRIPTION,
                   f"There is nothing special to see about the {item_name}."))
    print("--------------------\n")


def _resolve_direction(command):

    if len(command) not in (2, 3):
        return None

    if len(command) == 2:
        candidate = command[1]
    elif command[1] == General.AT:
        candidate = command[2]
    else:
        return None

    if candidate in allowed_directions:
        return candidate
    return None


def print_direction_info(location_name, direction):

    current_location = locations[location_name]

    if direction not in current_location:
        snarky_replies.print_snarky_reply_bad_direction()
        return

    adjacent_name = current_location[direction]
    if adjacent_name not in locations:
        snarky_replies.print_snarky_reply_bad_world(adjacent_name)
        return

    adjacent_location = locations[adjacent_name]
    view = adjacent_location.get(General.LOOK, "")
    visible_items = sorted(adjacent_location[General.ITEMS].keys())

    print(f"""
Direction Information:
    direction: {direction}
    location: {adjacent_name}
    description: {adjacent_location.get(General.DESCRIPTION, "")}
    view: {view}
    items: {visible_items}
""")


def look(location_name, command, inventory):

    current_location = locations[location_name]

    if len(command) == 1:
        print_location_info(location_name, current_location)
        return

    direction = _resolve_direction(command)
    if direction is not None:
        print_direction_info(location_name, direction)
        return

    if len(command) == 2:
        if command[1] == General.AT:
            snarky_replies.print_snarky_reply_bad_look_command()
            return
        item_name = command[1]
    elif len(command) == 3 and command[1] == General.AT:
        item_name = command[2]
    else:
        snarky_replies.print_snarky_reply_bad_look_command()
        return

    if item_name not in current_location[General.ITEMS] and item_name not in inventory:
        snarky_replies.print_snarky_reply_dont_have_item(item_name)
        return

    print_item_info(item_name, items.get(item_name, {}))


# -----------------------------------------------------------------
# Table-driven self tests (run only when this module is executed
# directly:  python actions/look.py)
# -----------------------------------------------------------------

def _snapshot(location_name, inventory):
    return copy.deepcopy({
        "location_name": location_name,
        "locations": locations,
        "inventory": inventory,
    })


def _run_case(row):

    location_name = row["loc"]
    inventory = copy.deepcopy(row.get("inventory", {}))
    output = io.StringIO()

    before = _snapshot(location_name, inventory)
    with redirect_stdout(output):
        look(location_name, copy.deepcopy(row["command"]), inventory)
    after = _snapshot(location_name, inventory)

    assert before == after, f"{row['name']}: look mutated world state"

    text = output.getvalue()
    for required in row.get("contains", []):
        assert required in text, f"{row['name']}: missing {required!r} in:\n{text}"
    for forbidden in row.get("forbids", []):
        assert forbidden not in text, f"{row['name']}: leaked {forbidden!r} in:\n{text}"

    output_repeat = io.StringIO()
    with redirect_stdout(output_repeat):
        look(location_name, copy.deepcopy(row["command"]), inventory)
    assert output_repeat.getvalue() == text, f"{row['name']}: repeated look changed output"
    assert _snapshot(location_name, inventory) == before, \
        f"{row['name']}: repeated look changed state"

    if row.get("extra") is not None:
        row["extra"](row, before, text)


def _check_determinism_under_item_order(row, before, text):

    from keywords import Direction, Location
    room = Location.WEST_ENTRY
    viewer = Location.WEST_HALLWAY
    saved_items = copy.deepcopy(locations[room][General.ITEMS])
    expected_list = "['baxter-the-dog', 'soccer-ball']"
    try:
        first_output = None
        for insertion_order in (
            (Item.SOCCER_BALL, Item.BAXTER),
            (Item.BAXTER, Item.SOCCER_BALL),
        ):
            locations[room][General.ITEMS] = {
                name: copy.deepcopy(items[name]) for name in insertion_order
            }
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                print_direction_info(viewer, Direction.WEST)
            output = buffer.getvalue()
            assert expected_list in output, "items must be sorted deterministically"
            assert "frisbee" not in output and "map" not in output, \
                "items from other areas leaked in"
            if first_output is None:
                first_output = output
            else:
                assert output == first_output, "direction output depends on traversal"
    finally:
        locations[room][General.ITEMS] = saved_items


def _check_failure_does_not_pollute(row, before, text):

    from keywords import Direction, Location
    target = Location.WEST_HALLWAY
    saved_direction = locations[target][Direction.NORTH]
    missing_name = "location-that-does-not-exist"
    try:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            print_direction_info(target, Direction.NORTH)
        healthy_output = buffer.getvalue()
        assert Location.CLASSROOM_SCIENCE in healthy_output

        locations[target][Direction.NORTH] = missing_name
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            print_direction_info(target, Direction.NORTH)
        failure_output = buffer.getvalue()
        assert missing_name in failure_output

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            print_direction_info(target, Direction.SOUTH)
        assert Location.CLASSROOM_MATH in buffer.getvalue()
    finally:
        locations[target][Direction.NORTH] = saved_direction

    assert _snapshot(target, {}) == before, "failed look polluted the world"


_TEST_CASES = [
    {
        "name": "bare look at entry",
        "loc": "schoolhouse-entry",
        "command": ["look"],
        "contains": ["schoolhouse-entry", "allowed directions: ['north']",
                     "items: ['map']"],
    },
    {
        "name": "bare look at foyer sorted output",
        "loc": "foyer",
        "command": ["look"],
        "contains": ["foyer", "allowed directions: ['east', 'north', 'south', 'west']",
                     "items: ['android-phone', 'globe']"],
    },
    {
        "name": "look north from entry",
        "loc": "schoolhouse-entry",
        "command": ["look", "north"],
        "contains": ["Direction Information", "foyer",
                     "items: ['android-phone', 'globe']"],
        "forbids": ["soccer-ball", "baxter-the-dog", "frisbee"],
    },
    {
        "name": "look at north synonym form",
        "loc": "schoolhouse-entry",
        "command": ["look", "at", "north"],
        "contains": ["direction: north", "location: foyer"],
        "forbids": ["soccer-ball", "frisbee"],
    },
    {
        "name": "examine north synonym verb",
        "loc": "schoolhouse-entry",
        "command": ["examine", "north"],
        "contains": ["direction: north"],
    },
    {
        "name": "study west from foyer",
        "loc": "foyer",
        "command": ["study", "west"],
        "contains": ["location: west-hallway", "items: []"],
        "forbids": ["soccer-ball", "baxter-the-dog"],
    },
    {
        "name": "display east from foyer",
        "loc": "foyer",
        "command": ["display", "east"],
        "contains": ["location: east-hallway", "items: []"],
        "forbids": ["frisbee"],
    },
    {
        "name": "look north from foyer shows back entry only",
        "loc": "foyer",
        "command": ["look", "north"],
        "contains": ["location: back-entry", "items: []"],
        "forbids": ["map", "globe", "soccer-ball", "frisbee"],
    },
    {
        "name": "look south from foyer",
        "loc": "foyer",
        "command": ["look", "south"],
        "contains": ["location: schoolhouse-entry", "items: ['map']"],
        "forbids": ["globe", "android-phone"],
    },
    {
        "name": "look direction with no exit bumps wall",
        "loc": "back-entry",
        "command": ["look", "north"],
        "contains": ["bump into a wall"],
        "forbids": ["Direction Information"],
    },
    {
        "name": "look west from west hallway shows only west entry items",
        "loc": "west-hallway",
        "command": ["look", "west"],
        "contains": ["location: west-entry",
                     "items: ['baxter-the-dog', 'soccer-ball']"],
        "forbids": ["frisbee", "globe", "map"],
    },
    {
        "name": "look east from west hallway returns foyer items",
        "loc": "west-hallway",
        "command": ["look", "at", "east"],
        "contains": ["items: ['android-phone', 'globe']"],
        "forbids": ["soccer-ball", "frisbee", "map"],
    },
    {
        "name": "repeat look same spot keeps output and state",
        "loc": "foyer",
        "command": ["look", "north"],
        "contains": ["back-entry"],
        "forbids": ["map"],
    },
    {
        "name": "look item in room",
        "loc": "schoolhouse-entry",
        "command": ["look", "map"],
        "contains": ["A map of the entire world"],
        "forbids": ["Direction Information"],
    },
    {
        "name": "look at item in room",
        "loc": "foyer",
        "command": ["look", "at", "globe"],
        "contains": ["antique globe"],
    },
    {
        "name": "look item held in inventory",
        "loc": "foyer",
        "command": ["look", "map"],
        "inventory": {Item.MAP: copy.deepcopy(items[Item.MAP])},
        "contains": ["A map of the entire world"],
    },
    {
        "name": "look missing item complains",
        "loc": "foyer",
        "command": ["look", "map"],
        "contains": ["I don't see map"],
        "forbids": ["A map of the entire world"],
    },
    {
        "name": "look item without description still succeeds",
        "loc": "west-entry",
        "command": ["look", "soccer-ball"],
        "contains": ["nothing special to see about the soccer-ball"],
    },
    {
        "name": "malformed look at with no target",
        "loc": "foyer",
        "command": ["look", "at"],
        "contains": ["How could I write my command so poorly"],
        "forbids": ["Direction Information"],
    },
    {
        "name": "malformed look with too many words",
        "loc": "foyer",
        "command": ["look", "at", "north", "now"],
        "contains": ["How could I write my command so poorly"],
    },
    {
        "name": "deterministic regardless of item traversal order",
        "loc": "foyer",
        "command": ["look", "west"],
        "extra": _check_determinism_under_item_order,
    },
    {
        "name": "failed look rolls back and does not pollute",
        "loc": "west-hallway",
        "command": ["look", "south"],
        "contains": ["classroom-math"],
        "extra": _check_failure_does_not_pollute,
    },
]


def run_self_tests():

    from keywords import Location

    pristine_world = copy.deepcopy(locations)

    for row in _TEST_CASES:
        _run_case(row)
        assert locations == pristine_world, \
            f"{row['name']}: world leaked between test cases"

    read_only_commands = [
        (Location.BACK_ENTRY, ["look", "north"]),
        (Location.BACK_ENTRY, ["examine", "wibble"]),
        (Location.BACK_ENTRY, ["look", "at"]),
        (Location.FOYER, ["look", "at", "north", "again"]),
        (Location.SCHOOLHOUSE_ENTRY, ["look", "no-such-item"]),
    ]
    for index, (room, command) in enumerate(read_only_commands):
        inventory = {}
        before = _snapshot(room, inventory)
        with redirect_stdout(io.StringIO()):
            look(room, copy.deepcopy(command), inventory)
        assert _snapshot(room, inventory) == before, \
            f"read-only case {index} mutated state"
        with redirect_stdout(io.StringIO()):
            look(room, ["look"], inventory)
    assert locations == pristine_world, "read-only cases polluted the world"

    for first, second in (
        (["look", "north"], ["look", "south"]),
        (["look", "south"], ["look", "north"]),
    ):
        buffer_a = io.StringIO()
        with redirect_stdout(buffer_a):
            look(Location.FOYER, copy.deepcopy(first), {})
        buffer_b = io.StringIO()
        with redirect_stdout(buffer_b):
            look(Location.FOYER, copy.deepcopy(second), {})
        buffer_a2 = io.StringIO()
        with redirect_stdout(buffer_a2):
            look(Location.FOYER, copy.deepcopy(first), {})
        assert buffer_a2.getvalue() == buffer_a.getvalue(), "order-dependent result"

    assert locations == pristine_world, "self tests left the world dirty"
    print(f"all {len(_TEST_CASES)} table-driven look cases passed")


if __name__ == "__main__":
    run_self_tests()
