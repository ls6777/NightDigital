#!/usr/bin/env python3
"""Generate the Night Digital watch face: the Watch Face Format XML and its
images.

The layout is computed from the screen radius, so the XML is generated
rather than written by hand. Run this after changing anything below, then
build with Gradle (build.sh does both).

Writes:
  watchface/src/main/res/raw/watchface.xml   the watch face
  watchface/src/main/res/drawable/hand_*.png the hands

With --test, the hands are frozen at TEST_TIME, to check the layout on the
emulator. build.sh test does this and then writes the normal XML back.

Needs Python 3 and Pillow.
"""

import math
import pathlib
import sys
import xml.etree.ElementTree as ET

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
RES = ROOT / "watchface" / "src" / "main" / "res"
DRAWABLE = RES / "drawable"

# --------------------------------------------------------------------- layout

#: Watch Face Format coordinate space. The face is scaled to the display.
SIZE = 450
#: Center and radius of the dial.
C = SIZE / 2
R = SIZE / 2

#: Where Night Dial's hour numerals 1 to 12 sat, which the heart rate (by
#: the 3), the UV index (by the 9) and the date (above the 6) are still
#: placed from. The numerals aren't drawn: they're only measured (see
#: measure_numerals). Drawn with Varela Round (SIL Open Font License,
#: tools/fonts/), thickened, with each "1" a plain bar with round ends.
#: Their digit height and how far their outer edges reach from the center,
#: in watch face units; the stroke width and the space between digits as
#: fractions of the digit height; and how much the font's digits are
#: narrowed.
NUMERALS = dict(height=20.0, reach=203.8, stroke=0.17, tracking=0.08, condense=0.9)
NUMERAL_FONT = ROOT / "tools" / "fonts" / "VarelaRound-Regular.ttf"

# --------------------------------------------------------------------- colors

ORANGE = "#FF8000"
#: The gauges' gray, for their tick marks (as measured from the gauge
#: reference).
GAUGE_GRAY = "#A4A4A4"
#: The readings' color, for every value and its words: the time, the
#: gauges' values and units (the battery percentage among them), the
#: battery hours, temperature, heart rate, UV "--", date and day name.
#: Their images are drawn in this white and tinted on the watch with the
#: color chosen in the watch face's settings (VALUE_TINT).
VALUE_COLOR = "#FFFFFF"
#: The choices for the readings' color in the watch face editor, the
#: first the default: (option id, its name's string resource, color).
#: Soft sky is softer than white and the orange's complement.
VALUE_COLORS = (("sky", "color_sky", "#BCD8F0"), ("ice", "color_ice", "#D6E7F5"),
                ("white", "color_white", "#FFFFFF"), ("cream", "color_cream", "#EDE3D2"),
                ("gray", "color_gray", "#B4B4B4"))
#: The tint that colors the readings: the chosen color (see VALUE_COLORS).
VALUE_TINT = "[CONFIGURATION.valueColor.0]"
#: A reached goal's green (DataDial's): the steps once they reach the goal.
GOAL_COLOR = "#3DDC57"


def polar(degrees, distance):
    """Point at an angle clockwise from 12 o'clock and a distance from the
    center."""
    a = math.radians(degrees)
    return C + distance * math.sin(a), C - distance * math.cos(a)


def fmt(v):
    """Short number for XML attributes."""
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


# ------------------------------------------------------------------ XML tools


def el(parent, tag, **attrs):
    """Add a child element. Attribute values may be numbers."""
    e = ET.SubElement(parent, tag)
    for k, v in attrs.items():
        e.set(k.rstrip("_"), fmt(v) if isinstance(v, float) else str(v))
    return e


def box(cx, cy, w, h):
    """Integer x, y, width, height of a box centered on (cx, cy)."""
    w, h = math.ceil(w), math.ceil(h)
    return {"x": round(cx - w / 2), "y": round(cy - h / 2), "width": w, "height": h}


def ambient_hide(parent):
    """Hide an element in always-on mode."""
    el(parent, "Variant", mode="AMBIENT", target="alpha", value="0")


def ambient_only(parent):
    """Show an element only in always-on mode (its alpha must be 0)."""
    el(parent, "Variant", mode="AMBIENT", target="alpha", value="255")


# ---------------------------------------------------------------- the scene


def user_configurations(face):
    """The watch face's settings, in the watch face editor: the readings'
    color (VALUE_COLORS), soft sky by default."""
    configs = el(face, "UserConfigurations")
    color = el(configs, "ColorConfiguration", id="valueColor",
               displayName="@string/value_color", defaultValue=VALUE_COLORS[0][0])
    for option, name, value in VALUE_COLORS:
        el(color, "ColorOption", id=option, displayName=f"@string/{name}", colors=value)


def bitmap_fonts(face):
    """The weather's image fonts: the condition icons by day and by night,
    one per [WEATHER.CONDITION] value (as text: "0" to "15"), and the
    temperature's characters."""
    fonts = el(face, "BitmapFonts")
    size = round(WEATHER_ICON["size"] * SCALE)
    for family, when in (("weather_icons_day", 0), ("weather_icons_night", 1)):
        font = el(fonts, "BitmapFont", name=family)
        for value, icons in enumerate(WEATHER_CONDITIONS):
            # One character per name, or a word for "10" and up.
            el(font, "Character" if value < 10 else "Word", name=str(value),
               resource=f"weather_{icons[when]}", width=size, height=size)
    for key in TEMPERATURE_COLORS:
        font = el(fonts, "BitmapFont", name=f"weather_temperature{temperature_set(key)}")
        for ch, name in TEMPERATURE_CHARS.items():
            w, h = TEMPERATURE_GLYPHS[name]
            el(font, "Character", name=ch, resource=f"weather_temp{temperature_set(key)}_{name}",
               width=w, height=h)
    # The day's low and high, beside the weather icon.
    font = el(fonts, "BitmapFont", name="weather_range")
    for ch, name in TEMPERATURE_CHARS.items():
        w, h = RANGE_GLYPHS[name]
        el(font, "Character", name=ch, resource=f"weather_range_{name}", width=w, height=h)
    # The date lines' characters, at the bottom.
    font = el(fonts, "BitmapFont", name="date_line")
    for ch, name in DATE_LINE_CHARS.items():
        w, h = DATE_LINE_GLYPHS[ch]
        el(font, "Character", name=ch, resource=f"date_line_{name}", width=w, height=h)
    # The date's digits.
    font = el(fonts, "BitmapFont", name="date_digits")
    for d, (w, h) in DATE_GLYPHS.items():
        el(font, "Character", name=d, resource=f"date_digit_{d}", width=w, height=h)
    # The heart rate's digits.
    font = el(fonts, "BitmapFont", name="hr_digits")
    for ch, name in HEART_RATE_CHARS.items():
        w, h = HR_GLYPHS[ch]
        el(font, "Character", name=ch, resource=f"hr_{name}", width=w, height=h)
    # The UV index's digits, a font per color (and the gray "heart_rate"
    # one, for its "--").
    for prefix in readout_sets():
        font = el(fonts, "BitmapFont", name=f"{prefix}_digits")
        for ch, name in HEART_RATE_CHARS.items():
            w, h = HEART_RATE_GLYPHS[ch]
            el(font, "Character", name=ch, resource=f"{prefix}_{name}", width=w, height=h)
    # The gauges' values: their gray digits.
    for family, prefix in (("gauge_digits", "gauge_digit"),
                           ("gauge_digits_goal", "gauge_digit_goal")):
        font = el(fonts, "BitmapFont", name=family)
        for ch, (w, h) in GAUGE_IMAGES["digits"].items():
            el(font, "Character", name=ch, resource=f"{prefix}_{GAUGE_CHARS[ch]}",
               width=w, height=h)
    # The time's, the seconds' and the battery hours' characters.
    for family, chars, glyphs in (("time", TIME_CHARS, TIME_GLYPHS),
                                  ("seconds", SECONDS_CHARS, SECONDS_GLYPHS),
                                  ("battery_hours", BATTERY_HOURS_CHARS, BATTERY_HOURS_GLYPHS),
                                  ("battery_hours_low", BATTERY_HOURS_CHARS,
                                   BATTERY_HOURS_GLYPHS)):
        font = el(fonts, "BitmapFont", name=f"{family}_digits")
        for ch, name in chars.items():
            w, h = glyphs[ch]
            el(font, "Character", name=ch, resource=f"{family}_{name}", width=w, height=h)
    # The big-number gauges' values, a font per size.
    for tier, sizes in enumerate(GAUGE_IMAGES["big_digits"]):
        for family, prefix in ((f"gauge_big{tier}_digits", f"gauge_big{tier}_digit"),
                               (f"gauge_big{tier}_digits_goal", f"gauge_big{tier}_digit_goal"),
                               (f"gauge_big{tier}_digits_low", f"gauge_big{tier}_digit_low")):
            font = el(fonts, "BitmapFont", name=family)
            for ch, (w, h) in sizes.items():
                el(font, "Character", name=ch, resource=f"{prefix}_{BIG_CHARS[ch]}",
                   width=w, height=h)


def text_part(parent, y, width, height, align="CENTER", x=0, tint=False, **text):
    """A PartText at (x, y) in the group, and its Text; with `tint`, in the
    readings' chosen color (VALUE_TINT)."""
    part = el(parent, "PartText", x=round(x), y=round(y), width=round(width),
              height=math.ceil(height), **({"tintColor": VALUE_TINT} if tint else {}))
    return el(part, "Text", align=align, **text)


def bitmap_text_part(parent, y, width, image_h, align="CENTER", x=0, tint=False):
    """A text_part for image font text whose images are `image_h` pixels
    tall, their tops at y: a pixel of room above and below, since the
    watch draws the images a little low in the box and clips a box only as
    tall as they are (the digits' tops came out flat). `tint` as for
    text_part."""
    return text_part(parent, round(y) - 1, width, image_h + 2, align=align, x=x, tint=tint)


def template(parent, fmt, *expressions):
    """A Template of fmt with a Parameter per expression."""
    t = el(parent, "Template")
    t.text = fmt
    for e in expressions:
        el(t, "Parameter", expression=e)


def weather_layout():
    """Where the weather display's parts go: a dict of the group's box on
    the face ("x", "y", "width", "height"), and in the group the text
    column's left edge ("text_x"), the temperature's top ("temp_y") and the
    icon's top left ("icon_x", "icon_y"), in watch face units."""
    cx, cy = WEATHER["text_center"]
    ix, iy = WEATHER["icon_center"]
    icon, block = WEATHER_ICON["size"], WEATHER["temperature"]
    # The text column's and the icon's boxes on the face, and the group
    # around both. The text is centered in its column, so the column moves
    # right by half the degree sign and the digits' trailing spacing,
    # which centers the digits' ink on `text_center`.
    trailing = GAUGE_FONT["tracking"] * WEATHER["temperature"]
    cx += (TEMPERATURE_GLYPHS["degree"][0] + trailing) / 2
    tx, ty = cx - WEATHER["text_width"] / 2, cy - block / 2
    icon_left, icon_top = ix - icon / 2, iy - icon / 2
    x0, y0 = math.floor(min(tx, icon_left)), math.floor(min(ty, icon_top))
    x1 = max(tx + WEATHER["text_width"], icon_left + icon)
    y1 = max(ty + block, icon_top + icon)
    return dict(x=x0, y=y0, width=math.ceil(x1 - x0), height=math.ceil(y1 - y0),
                text_x=tx - x0, temp_y=ty - y0, icon_x=icon_left - x0, icon_y=icon_top - y0)


def battery_icon(parent, level, cx, top):
    """The battery icon under parent, centered on cx with its top at top:
    the image with a segment lit per 20% (rounded up) of the expression
    `level`, orange, or red below BATTERY_LOW's limit."""
    iw, ih = BATTERY_IMAGES["icon"]
    n, limit = BATTERY["segments"], BATTERY_LOW["limit"]
    step = 100 / n
    low = el(parent, "Condition")
    el(el(low, "Expressions"), "Expression", name="low").text = f"{level} < {limit}"
    for branch, (lowest, highest), suffix in (
            (el(low, "Compare", expression="low"), (0, battery_segments(limit - 1)), "_low"),
            (el(low, "Default"), (battery_segments(limit), n), "")):
        # The image with as many segments lit as the level calls for, the
        # fewest by default. Each image's range excludes the others: when
        # the level changes, the runtime moves off a Compare that turns
        # false only to one that turns true, or else to the Default, so
        # overlapping ranges (> 60 still true when > 80 turns false) would
        # leave the Default showing.
        lit = el(branch, "Condition")
        exprs = el(lit, "Expressions")
        images = []
        for k in range(highest, lowest, -1):
            expression = f"{level} > {fmt((k - 1) * step)}"
            if k < highest:
                expression += f" && {level} <= {fmt(k * step)}"
            el(exprs, "Expression", name=f"lit{k}").text = expression
            images.append((el(lit, "Compare", expression=f"lit{k}"), k))
        for b, k in images + [(el(lit, "Default"), lowest)]:
            part = el(b, "PartImage", x=round(cx - iw / 2), y=round(top), width=iw, height=ih)
            el(part, "Image", resource=f"battery{suffix}_{k}")


def gauge(scene, spec, sample=None):
    """A gauge (see GAUGE and GAUGES): its dial, the pointer turned to its
    value on the scale, the hub over it, its value below the hub and its
    icon below that. Hidden in always-on mode. A gauge with a complication
    takes its value from the complication slot (see gauge_complication).
    sample maps data sources ("[MONTH]") to fixed values to show instead (see
    TEST_SOURCES), for the test build, which has no complication slot."""
    def expression(e):
        """An expression with the sample's values for its data sources."""
        for source, value in (sample or {}).items():
            e = e.replace(source, str(value))
        return e

    gx, gy = gauge_center(spec)
    size = GAUGE_IMAGES[f"{spec['name']}_dial"]
    b = box(gx, gy, size, size)
    group = el(scene, "Group", name=f"{spec['name']}Gauge", **b)
    ambient_hide(group)
    cx, cy = gx - b["x"], gy - b["y"]  # the gauge center in the group
    if "complication" in spec and sample is not None:
        # The test build: the bar at the sample's number.
        c = spec["complication"]
        kind = c["types"][c["test"]]
        number = kind["number"]
        for source, value in c["sample"].items():
            number = number.replace(source, str(value))
        gauge_face(group, spec, size, (cx, cy), bar=expression(number))
    else:
        gauge_face(group, spec, size, (cx, cy),
                   bar=expression(spec["number"]) if "number" in spec else None)

    if "complication" in spec and sample is None:
        # The slot draws nothing while its source has no data, so the gauge
        # without data goes under it, and each of its readings covers that.
        gauge_reading(group, spec, size, (cx, cy), str(spec["scale"][0]), None)
        gauge_complication(scene, spec, b, (cx, cy))
    elif "complication" in spec:
        # The test build: the sample complication text, read as the watch
        # reads the complication's.
        c = spec["complication"]

        def sampled(e):
            for source, value in c["sample"].items():
                e = e.replace(source, str(value))
            return expression(e)
        kind = c["types"][c["test"]]
        gauge_reading(group, spec, size, (cx, cy),
                      sampled(spec["pointer"].replace(c["source"], kind["number"])),
                      sampled(kind["value"]),
                      sampled(kind["available"]) if "available" in kind else None,
                      sampled(kind.get("fallback", '"--"')),
                      sampled(kind["goal"]) if "goal" in kind else None,
                      sampled(kind["number"]))
    else:
        gauge_reading(group, spec, size, (cx, cy), expression(spec["pointer"]),
                      expression(spec["value"]),
                      expression(spec["available"]) if "available" in spec else None,
                      number=expression(spec["number"]) if "number" in spec else None,
                      low_when=expression(spec["low"]) if "low" in spec else None)


def gauge_value_layout(spec, cy, tier=0):
    """Where a gauge's value and icon go, for the gauge center's y `cy`:
    (value top, value image height, value font, its goal font, its digit
    height, icon top), in watch face units. Below the hub as usual; for a
    big-number gauge (see BIG_VALUE), its value at size `tier` centered on
    the gauge center, and its icon at the bottom, its bottom edge
    BIG_VALUE's `icon_bottom` below the center."""
    if spec.get("big"):
        vh = GAUGE_IMAGES["big_digits"][tier]["0"][1]
        ih = GAUGE_IMAGES[spec["icon"]][1] if "icon" in spec else 0
        return (cy - vh / 2, vh, f"gauge_big{tier}_digits", f"gauge_big{tier}_digits_goal",
                BIG_VALUE["sizes"][tier][1], cy + BIG_VALUE["icon_bottom"] - ih)
    return (cy + GAUGE["hub"][0][0] + GAUGE["value"]["gap"], GAUGE_IMAGES["digits"]["0"][1],
            "gauge_digits", "gauge_digits_goal", GAUGE["value"]["height"], gauge_icon_top(cy))


def big_tier(value):
    """The BIG_VALUE size tier for a number."""
    return next(i for i, (below, _) in enumerate(BIG_VALUE["sizes"])
                if below is None or abs(value) < below)


def gauge_bar(parent, spec, size, center, number):
    """A gauge's progress bar (see GAUGE's `bar`) under parent: an arc
    along its tick ring from the scale's low end, as far round as the
    expression `number` is along the scale (held at the ends), the whole
    bar in the color of the stretch it has reached (the gauge's own
    `bar_colors`, if it has them), and the marker dot at its end."""
    cx, cy = center
    lo, hi = spec["scale"]
    bar = GAUGE["bar"]
    fraction = f"clamp(({number} - {fmt(lo)}) / {fmt(hi - lo)}, 0, 1)"
    radius = gauge_ring(spec)[0] + gauge_ring(spec)[1] / 2
    start = gauge_angle(spec, lo)
    # One color per stretch: ranges that exclude each other (the runtime
    # skips a Compare that was already true).
    colors = spec.get("bar_colors", bar["colors"])

    def arc_in(under, color):
        """The bar, in `color`, under `under`."""
        draw = el(under, "PartDraw", x=0, y=0, width=size, height=size)
        arc = el(draw, "Arc", centerX=cx, centerY=cy, width=2 * radius, height=2 * radius,
                 startAngle=start, endAngle=start, direction="CLOCKWISE")
        el(arc, "Stroke", color=color, thickness=bar["width"], cap="ROUND")
        # The arc's end turned round from its start by the fraction reached.
        el(arc, "Transform", target="endAngle",
           value=f"{fmt(start)} + {fraction} * {fmt(gauge_arc(spec))}")

    if len(colors) == 1:
        arc_in(parent, colors[0][1])
    else:
        colored = el(parent, "Condition")
        exprs = el(colored, "Expressions")
        lows = [None] + [below for below, _ in colors[:-1]]
        for i, ((below, _), low) in enumerate(zip(colors, lows)):
            parts = ([f"{fraction} >= {fmt(low)}"] if low is not None else []) + \
                    ([f"{fraction} < {fmt(below)}"] if below is not None else [])
            el(exprs, "Expression", name=f"bar{i}").text = " && ".join(parts)
        for i, (_, color) in enumerate(colors):
            arc_in(el(colored, "Compare", expression=f"bar{i}"), color)

    # The marker dot at the bar's end (see GAUGE's `dot`): drawn at 12 and
    # turned about the gauge center with the bar.
    dot = GAUGE["dot"]
    draw = el(parent, "PartDraw", x=0, y=0, width=size, height=size, pivotX=fmt(cx / size),
              pivotY=fmt(cy / size), angle=fmt(start))
    for r, color in ((dot["radius"] + dot["edge"], "#000000"), (dot["radius"], dot["color"])):
        el(el(draw, "Ellipse", x=cx - r, y=cy - radius - r, width=2 * r, height=2 * r), "Fill",
           color=color)
    el(draw, "Transform", target="angle",
       value=f"{fmt(start)} + {fraction} * {fmt(gauge_arc(spec))}")


def gauge_face(parent, spec, size, center, cover=False, bar=None):
    """A gauge's still parts under parent: its dial and its icon; with
    `cover`, on a black disc that hides whatever is under the gauge; with
    `bar`, an expression for its number, its progress bar over the dial's
    ticks (see gauge_bar). The battery gauge's icon is the battery at that
    number (see battery_icon)."""
    cx, cy = center
    if cover:
        disc = el(parent, "PartDraw", **box(cx, cy, size, size))
        el(el(disc, "Ellipse", x=0, y=0, width=size, height=size), "Fill", color="#000000")
    dial = el(parent, "PartImage", **box(cx, cy, size, size))
    el(dial, "Image", resource=f"{spec['name']}_dial")
    if bar is not None:
        gauge_bar(parent, spec, size, center, bar)
    if spec.get("icon") == "battery" and bar is not None:
        battery_icon(parent, bar, cx, gauge_value_layout(spec, cy)[5])
    elif "icon" in spec:
        iw, ih = GAUGE_IMAGES[spec["icon"]]
        icon = el(parent, "PartImage", x=round(cx - iw / 2),
                  y=round(gauge_value_layout(spec, cy)[5]), width=iw, height=ih)
        el(icon, "Image", resource=spec["icon"])


def gauge_reading(parent, spec, size, center, pointer, value, available=None,
                  fallback='"--"', goal=None, number=None, low_when=None):
    """A gauge's moving parts under parent: the expression `value` in
    digits below the hub (or `fallback`, "--" unless given, while
    `available` is false, or always with no `value`; in green while the
    expression `goal` is true, in red while the expression `low_when` is
    true), the pointer over it turned to the
    expression `pointer` on its scale, and the hub; a big-number gauge has
    no pointer or hub, only its large value, at the size that fits its
    digits (by the expression `number`, see BIG_VALUE), with its unit
    label above it. center is the gauge center in parent."""
    cx, cy = center
    # The value, centered below the hub, under the pointer (which sweeps
    # over it, as over the labels). Each digit image ends in the digits'
    # spacing, so the box moves right by half of it. The font's size is its
    # images' height, so the watch draws them at their own size (at
    # another, it scales them, softer, and clips their tops), in a box with
    # room to spare.
    def value_at(under, tier=0):
        """The value (or "--", or the fallback) under `under` at size `tier`,
        and a big value's unit label above it."""
        top_y, image_h, plain, green, height, _ = gauge_value_layout(spec, cy, tier)
        trailing = GAUGE_FONT["tracking"] * height

        def value_text(at, shown, family=plain):
            """The value's text part under `at`, showing `shown`."""
            text = el(at, "PartText", x=round(trailing / 2), y=round(top_y) - 1, width=size,
                      height=image_h + 2,
                      **({"tintColor": VALUE_TINT} if family == plain else {}))
            t = el(text, "Text", align="CENTER")
            template(el(t, "BitmapFont", family=family, size=image_h), "%s", shown)

        if "unit_label" in spec:
            uw, uh = GAUGE_IMAGES[f"unit_{spec['name']}"]
            uy = cy - spec["unit_top"] if "unit_top" in spec else \
                top_y - BIG_VALUE["unit_gap"] - uh
            unit = el(under, "PartImage", x=round(cx - uw / 2), y=round(uy), width=uw,
                      height=uh, tintColor=VALUE_TINT)
            el(unit, "Image", resource=f"unit_{spec['name']}")
        assert goal is None or available is None, "a goal with a fallback isn't drawn"
        assert low_when is None or (goal is None and available is None),             "low_when only on its own"
        if value is None:
            value_text(under, '"--"')
        elif low_when is not None:
            warn = el(under, "Condition")
            el(el(warn, "Expressions"), "Expression", name="low").text = low_when
            value_text(el(warn, "Compare", expression="low"), value, f"{plain}_low")
            value_text(el(warn, "Default"), value)
        elif goal is not None:
            met = el(under, "Condition")
            el(el(met, "Expressions"), "Expression", name="goalMet").text = goal
            value_text(el(met, "Compare", expression="goalMet"), value, green)
            value_text(el(met, "Default"), value)
        elif available is None:
            value_text(under, value)
        else:
            # Without data, the fallback in the value's place.
            shown = el(under, "Condition")
            el(el(shown, "Expressions"), "Expression", name="available").text = available
            value_text(el(shown, "Compare", expression="available"), value)
            value_text(el(shown, "Default"), fallback)

    if not spec.get("big"):
        value_at(parent)
    elif value is None or number is None:
        value_at(parent)  # "--": the largest size
    else:
        # The size by the number's digits: ranges that exclude each other
        # (the runtime skips a Compare that was already true).
        sized = el(parent, "Condition")
        exprs = el(sized, "Expressions")
        lows = [None] + [below for below, _ in BIG_VALUE["sizes"][:-1]]
        for tier, ((below, _), low) in enumerate(zip(BIG_VALUE["sizes"], lows)):
            parts = ([f"abs({number}) >= {low}"] if low is not None else []) + \
                    ([f"abs({number}) < {below}"] if below is not None else [])
            el(exprs, "Expression", name=f"size{tier}").text = " && ".join(parts)
        for tier in range(len(BIG_VALUE["sizes"])):
            branch = el(el(sized, "Compare", expression=f"size{tier}"), "Group",
                        name=f"{spec['name']}Size{tier}", x=0, y=0, width=size, height=size)
            value_at(branch, tier)
        # A number that isn't one (text such as "--" read as nothing) matches
        # no size: the largest, as for "--".
        value_at(el(el(sized, "Default"), "Group", name=f"{spec['name']}SizeDefault",
                    x=0, y=0, width=size, height=size))

    if spec.get("big"):
        return
    # The pointer, its pivot at the gauge center, turned from the scale's
    # low end by its value.
    w, top, bottom = HAND_IMAGES["gauge_pointer"]
    lo, hi = spec["scale"]
    part = el(parent, "PartImage", x=round(cx - w / 2), y=round(cy - top), width=w,
              height=top + bottom, pivotX=0.5, pivotY=top / (top + bottom))
    el(part, "Image", resource="gauge_pointer")
    # Degrees per unit as a fraction: fmt() rounds to two decimals, which
    # for a long scale (288 / 15000 = 0.0192 as 0.02) overshoots the end.
    el(part, "Transform", target="angle",
       value=f"{fmt(gauge_angle(spec, lo))} + ({pointer} - {fmt(lo)}) * "
             f"{fmt(gauge_arc(spec))} / {fmt(hi - lo)}")

    hub_size = GAUGE_IMAGES["hub"]
    hub_part = el(parent, "PartImage", **box(cx, cy, hub_size, hub_size))
    el(hub_part, "Image", resource="gauge_hub")


def gauge_complication(scene, spec, bounds, center):
    """A gauge's complication slot, covering the gauge (`bounds`, its box
    on the face), filled from its data source (see GAUGES) and not
    changeable in the watch face editor. It goes straight in the scene:
    the runtime only connects data sources to slots there (one inside a
    Group draws, but never gets data). Hidden in always-on mode. For each
    complication type the gauge takes, the whole gauge over the one
    without data (see gauge), its moving parts with the gauge's value
    source replaced by that type's number; and for an empty slot, the
    gauge without data again. center is the gauge center in the slot."""
    c = spec["complication"]
    size = bounds["width"]
    slot = el(scene, "ComplicationSlot", **bounds, slotId=c["slot"], name=f"{spec['name']}Slot",
              supportedTypes=" ".join(list(c["types"]) + ["EMPTY"]), isCustomizable="FALSE")
    ambient_hide(slot)
    el(slot, "DefaultProviderPolicy", defaultSystemProvider="EMPTY",
       defaultSystemProviderType="EMPTY", primaryProvider=c["provider"],
       primaryProviderType=c["provider_type"])
    el(slot, "BoundingOval", x=0, y=0, width=size, height=size)
    for kind, k in c["types"].items():
        comp = el(slot, "Complication", type=kind)
        gauge_face(comp, spec, size, center, cover=True, bar=k["number"])
        gauge_reading(comp, spec, size, center,
                      spec["pointer"].replace(c["source"], k["number"]), k["value"],
                      k.get("available"), k.get("fallback", '"--"'), k.get("goal"),
                      k["number"])
    gauge_reading(el(slot, "Complication", type="EMPTY"), spec, size, center,
                  str(spec["scale"][0]), None)


def readout_layout(center, glyphs, height, icon, gap):
    """Where a readout's parts go (the heart rate's, the UV index's): its
    value in a column three of its widest digit wide, centered on `center`
    (x on the face), with its icon (width, height) centered `gap` above
    it, the two together centered on the time vertically. glyphs are the
    value's digit image sizes, `height` units tall. Returns the column's
    left edge and width, the value's top, and the icon's left and top, in
    watch face units."""
    iw, ih = icon
    dh = glyphs["0"][1]
    width = 3 * max(glyphs[d][0] for d in "0123456789")
    # Each digit image ends in the font's spacing, so the centered text's
    # ink sits that much left of the column's middle.
    value_left = center - width / 2 + GAUGE_FONT["tracking"] * height / 2
    _, clock_top, _, clock_h = clock_box()
    value_top = clock_top + clock_h / 2 - (ih + gap + dh) / 2 + ih + gap
    return value_left, width, value_top, center - iw / 2, value_top - gap - ih


def heart_rate(scene, sample=None):
    """The heart rate (see HEART_RATE) by the 3: the rate in its digits,
    centered, or "--" without a reading (the watch gives an empty value,
    which counts as 0), and the red heart centered above it, the two
    centered on the time vertically (see readout_layout). Hidden in
    always-on mode. sample maps data sources to fixed values (see
    TEST_SOURCES)."""
    hr = str((sample or {}).get("[HEART_RATE]", "[HEART_RATE]"))
    iw, ih = GAUGE_IMAGES["gauge_heart"]
    dw, dh = HR_GLYPHS["0"]  # the font's size is its images' height
    value_left, width, value_top, heart_left, heart_top = readout_layout(
        SIZE - HEART_RATE["edge"], HR_GLYPHS, HEART_RATE["value"], (iw, ih),
        HEART_RATE["heart_gap"])
    left = math.floor(value_left)
    top = math.floor(heart_top) - 1
    group = el(scene, "Group", name="heartRate", x=left, y=top,
               width=math.ceil(value_left + width) - left,
               height=math.ceil(value_top + dh + 2) - top)
    ambient_hide(group)
    heart = el(group, "PartImage", x=round(heart_left) - left, y=round(heart_top) - top,
               width=iw, height=ih)
    el(heart, "Image", resource="gauge_heart")
    shown = el(group, "Condition")
    el(el(shown, "Expressions"), "Expression", name="hasHeartRate").text = f"{hr} > 0"
    for branch, value in ((el(shown, "Compare", expression="hasHeartRate"), f"round({hr})"),
                          (el(shown, "Default"), '"--"')):
        t = bitmap_text_part(branch, value_top - top, width, dh, x=round(value_left) - left,
                             tint=True)
        template(el(t, "BitmapFont", family="hr_digits", size=dh), "%s", value)


def date_line(scene, sample=None):
    """The day of the week above the month and date (see DATE_LINE): the
    day's three letters ("WED"), centered; and the month's ("NOV") and the
    day of the month along the bottom of the screen, centered on the arc,
    reading left to right with their tops toward the center. Hidden in
    always-on mode. sample maps data sources to fixed values (see
    TEST_SOURCES)."""
    def source(name):
        return str((sample or {}).get(name, name))

    h = DATE_LINE_GLYPHS["0"][1]  # the font's size is its images' height
    trailing = GAUGE_FONT["tracking"] * DATE_LINE["height"]
    # The month and date's baseline: `bottom` above the screen's bottom.
    baseline = R - DATE_LINE["bottom"]
    day_top = SIZE - DATE_LINE["bottom"] - h - DATE_LINE["spacing"] - h
    x7, _, w7, _ = NUMERAL_BOXES[7]
    x5, _, w5, _ = NUMERAL_BOXES[5]
    left, right = x7 + w7 / 2, x5 - w5 / 2

    def by_value(parent, src, count, prefix, part):
        """A text per value of `src` (1 for the first) under parent, each
        its own exact value so the Compares never overlap; part(branch, n)
        draws value n's under its branch."""
        shown = el(parent, "Condition")
        exprs = el(shown, "Expressions")
        for n in range(1, count + 1):
            el(exprs, "Expression", name=f"{prefix}{n}").text = f"{source(src)} == {n}"
        for n in range(1, count + 1):
            part(el(shown, "Compare", expression=f"{prefix}{n}"), n)

    # The day, centered (each character image ends in the font's spacing).
    top = round(day_top) - 1
    group = el(scene, "Group", name="dayLine", x=round(left), y=top,
               width=round(right - left), height=math.ceil(day_top + h + 1) - top)
    ambient_hide(group)

    def day(branch, n):
        t = bitmap_text_part(branch, day_top - top, right - left, h, x=round(trailing / 2),
                             tint=True)
        template(el(t, "BitmapFont", family="date_line", size=h), "%s",
                 f'"{DAY_NAMES[n - 1][:3]}"')
    # [DAY_OF_WEEK] is 1 for Sunday.
    by_value(group, "[DAY_OF_WEEK]", 7, "day", day)

    # The month and date along the bottom, reading counter-clockwise (left
    # to right there), centered on the bottom: the arc's middle moves a
    # half spacing toward the end, past the last character's.
    group = el(scene, "Group", name="dateLine", x=0, y=0, width=SIZE, height=SIZE)
    ambient_hide(group)
    span = math.degrees(DATE_LINE["arc_width"] / baseline)
    middle = 180 - math.degrees(trailing / 2 / baseline)

    def month(branch, n):
        part = el(branch, "PartText", x=0, y=0, width=SIZE, height=SIZE, tintColor=VALUE_TINT)
        t = el(part, "TextCircular", centerX=C, centerY=C, width=2 * baseline,
               height=2 * baseline, startAngle=fmt(middle + span / 2),
               endAngle=fmt(middle - span / 2), direction="COUNTER_CLOCKWISE", align="CENTER")
        template(el(t, "BitmapFont", family="date_line", size=h), f"{MONTH_NAMES[n - 1]} %s",
                 source("[DAY]"))
    by_value(group, "[MONTH]", 12, "month", month)


def day_date(scene, sample=None):
    """The day of the week and the date (see DAY_DATE), in the gauges'
    gray: the day's name just right of the hub and the day of the month
    above the hub, between it and the top gauges. Hidden in always-on mode. sample maps data sources to fixed
    values (see TEST_SOURCES)."""
    def source(name):
        return str((sample or {}).get(name, name))

    nw, nh = DAY_IMAGES["SUNDAY"]
    digit_h = DATE_GLYPHS["0"][1]
    width = DAY_DATE["width"]
    # The name right of the hub, level with it, centered between the hub's
    # edge and where a two-digit UV index starts (then moved right a
    # little); the date above the hub, centered between it and the top
    # gauges' row, where they come closest to each other.
    hub = DAY_DATE["hub"]
    rows = sorted({round(gauge_center(spec)[1], 3) for spec in GAUGES})
    name_top = C - nh / 2
    date_top = ((C - hub) + rows[0]) / 2 - digit_h / 2 + DAY_DATE["date_down"]
    name_left = C + hub + DAY_DATE["name_right"]  # the centered box, moved right
    name_w = uv_layout()["two_digits_left"] - (C + hub)
    group = el(scene, "Group", name="dayName", x=round(name_left), y=round(name_top),
               width=round(name_w), height=nh)
    ambient_hide(group)
    # The day's name: an image per day ([DAY_OF_WEEK] is 1 for Sunday), each
    # its own exact value, so the Compares never overlap.
    day = el(group, "Condition")
    exprs = el(day, "Expressions")
    for n, name in enumerate(DAY_NAMES, start=1):
        el(exprs, "Expression", name=f"day{n}").text = f"{source('[DAY_OF_WEEK]')} == {n}"
    for n, name in enumerate(DAY_NAMES, start=1):
        w, h = DAY_IMAGES[name]
        part = el(el(day, "Compare", expression=f"day{n}"), "PartImage",
                  x=round((name_w - w) / 2), y=0, width=w, height=h)
        el(part, "Image", resource=f"day_{name.lower()}")
    # The date, centered; each digit image ends in the digits' spacing.
    group = el(scene, "Group", name="date", x=round(C - width / 2), y=round(date_top) - 1,
               width=round(width), height=digit_h + 2)
    ambient_hide(group)
    trailing = GAUGE_FONT["tracking"] * DAY_DATE["date"]
    t = bitmap_text_part(group, 1, width, digit_h, x=round(trailing / 2), tint=True)
    template(el(t, "BitmapFont", family="date_digits", size=digit_h), "%s", source("[DAY]"))


def uv_layout():
    """Where the UV index's column goes, by the 9, the heart rate's mirror
    image, in watch face units on the face: its center ("cx") and width
    ("width", three digits wide, its left edge HEART_RATE's `inset` right
    of the 9, less UV's `icon_out`), and where its index's ink starts ("two_digits_left": the
    index is left-aligned, UV's `value_in` inside the column, and a
    two-digit one starts with a 1, whose stroke starts right of its image's
    edge)."""
    dw = HEART_RATE_GLYPHS["0"][0]
    x9, _, w9, _ = NUMERAL_BOXES[9]
    width = 3 * dw
    left = x9 + w9 / 2 + HEART_RATE["inset"] - UV["icon_out"]
    one = Image.open(DRAWABLE / "heart_rate_1.png").getchannel("A").getbbox()[0] / SCALE
    return dict(cx=left + width / 2, width=width,
                two_digits_left=left + UV["value_in"] + one)


def uv_index(scene, sample=None):
    """The UV index by the 9, laid out as the heart rate is: the index,
    centered, in the WHO level's color (see UV_LEVELS), or "--" without
    weather data (0 with weather but no index, as at night), and DataDial's
    "UV" icon, orange, centered above it, the two centered on the time
    vertically (see readout_layout). Hidden in always-on mode. sample is
    fixed weather to show instead (see TEST_WEATHER)."""
    def w(source):
        """The expression for a weather data source, or its sample value."""
        return str(sample[source]) if sample else f"[WEATHER.{source}]"

    iw, ih = GAUGE_IMAGES["gauge_uv"]
    dh = HEART_RATE_GLYPHS["0"][1]  # the font's size is its images' height
    value_left, width, value_top, icon_left, icon_top = readout_layout(
        UV["edge"], HEART_RATE_GLYPHS, HEART_RATE["digits"], (iw, ih), UV["icon_gap"])
    x0 = math.floor(value_left)
    top = math.floor(icon_top) - 1
    group = el(scene, "Group", name="uvIndex", x=x0, y=top,
               width=math.ceil(value_left + width) - x0,
               height=math.ceil(value_top + dh + 2) - top)
    ambient_hide(group)
    icon = el(group, "PartImage", x=round(icon_left) - x0, y=round(icon_top) - top, width=iw,
              height=ih)
    el(icon, "Image", resource="gauge_uv")
    value_x = round(value_left) - x0
    uv, available = f"round({w('UV_INDEX')})", w("IS_AVAILABLE")
    # Mutually exclusive ranges (the runtime skips a Compare that was already
    # true), each level's lowest index up to the next one's.
    level = el(group, "Condition")
    exprs = el(level, "Expressions")
    bounds = [lo for _, lo, _ in UV_LEVELS] + [None]
    for (name, lo, _), hi in zip(UV_LEVELS, bounds[1:]):
        e = f"({available}) && {uv} >= {lo}" + (f" && {uv} < {hi}" if hi is not None else "")
        el(exprs, "Expression", name=f"uv_{name}").text = e
    # Without weather data, "--" (exclusive of the levels, which need it).
    el(exprs, "Expression", name="uv_none").text = f"!({available})"
    for (name, _, _) in UV_LEVELS:
        t = bitmap_text_part(el(level, "Compare", expression=f"uv_{name}"), value_top - top,
                             width, dh, x=value_x)
        template(el(t, "BitmapFont", family=f"uv_{name}_digits", size=dh), "%s", uv)
    t = bitmap_text_part(el(level, "Compare", expression="uv_none"), value_top - top, width, dh,
                         x=value_x, tint=True)
    template(el(t, "BitmapFont", family="heart_rate_digits", size=dh), "%s", '"--"')
    # Weather but no index (the watch reports none at night): 0, as DataDial
    # shows it, in the lowest level's color.
    t = bitmap_text_part(el(level, "Default"), value_top - top, width, dh, x=value_x)
    template(el(t, "BitmapFont", family=f"uv_{UV_LEVELS[0][0]}_digits", size=dh), "%s", '"0"')


def weather(scene, sample=None):
    """The weather display (see WEATHER): the condition's icon and the
    temperature. Without weather data, the sun and "--°" in their place.
    Hidden in always-on mode. sample
    is fixed weather to show instead (see TEST_WEATHER), for the test build."""
    def w(source):
        """The expression for a weather data source, or its sample value."""
        return str(sample[source]) if sample else f"[WEATHER.{source}]"

    icon, temp = WEATHER_ICON["size"], WEATHER["temperature"]
    layout = weather_layout()
    width, height = layout["width"], layout["height"]
    text_w = WEATHER["text_width"]
    group = el(scene, "Group", name="weather", x=layout["x"], y=layout["y"], width=width,
               height=height)
    ambient_hide(group)
    shown = el(group, "Condition")
    el(el(shown, "Expressions"), "Expression", name="available").text = w("IS_AVAILABLE")
    content = el(el(shown, "Compare", expression="available"), "Group", name="weatherShown",
                 x=0, y=0, width=round(width), height=math.ceil(height))
    # No weather data: the sun and "--°".
    none = el(el(shown, "Default"), "Group", name="weatherNone", x=0, y=0,
              width=round(width), height=math.ceil(height))
    sun = el(none, "PartImage", x=round(layout["icon_x"]), y=round(layout["icon_y"]),
             width=round(icon), height=round(icon))
    el(sun, "Image", resource="weather_clear_day")
    t = bitmap_text_part(none, layout["temp_y"], text_w, TEMPERATURE_GLYPHS["0"][1],
                         x=layout["text_x"], tint=True)
    template(el(t, "BitmapFont", family="weather_temperature",
                size=TEMPERATURE_GLYPHS["0"][1]), "%s", '"--°"')

    # The icon: the day or night set, by the condition's value.
    day = el(content, "Condition")
    el(el(day, "Expressions"), "Expression", name="isDay").text = w("IS_DAY")
    for branch, family in ((el(day, "Compare", expression="isDay"), "weather_icons_day"),
                           (el(day, "Default"), "weather_icons_night")):
        t = text_part(branch, layout["icon_y"], icon, icon, x=layout["icon_x"])
        template(el(t, "BitmapFont", family=family, size=icon), "%s",
                 f"{w('CONDITION')} <= 15 ? {w('CONDITION')} : 0")

    # The temperature, without its unit (the watch's own setting), colored
    # by how hot or cold it is (in °F). As on DataDial, unit 2 is
    # Fahrenheit and any other Celsius.
    in_f = f'{w("TEMPERATURE_UNIT")} == 2'
    fahrenheit = f"({in_f} ? {w('TEMPERATURE')} : {w('TEMPERATURE')} * 9 / 5 + 32)"
    colored = el(content, "Condition")
    exprs = el(colored, "Expressions")
    el(exprs, "Expression", name="hot").text = f"{fahrenheit} > {TEMPERATURE_LIMITS['hot']}"
    el(exprs, "Expression", name="cold").text = f"{fahrenheit} < {TEMPERATURE_LIMITS['cold']}"
    for branch, key in ((el(colored, "Compare", expression="hot"), "hot"),
                        (el(colored, "Compare", expression="cold"), "cold"),
                        (el(colored, "Default"), "")):
        # The normal temperature in the chosen color; hot and cold keep theirs.
        t = bitmap_text_part(branch, layout["temp_y"], text_w, TEMPERATURE_GLYPHS["0"][1],
                             x=layout["text_x"], tint=key == "")
        template(el(t, "BitmapFont", family=f"weather_temperature{temperature_set(key)}",
                    size=TEMPERATURE_GLYPHS["0"][1]), "%s°", w("TEMPERATURE"))



def range_arc():
    """The arc the day's low and high follow (see WEATHER's `range`): the
    radius of their middle (WEATHER's `range_out` beyond the weather
    icon's middle, toward the screen's edge) and of their baseline, about
    the face center, in watch face units."""
    middle = C - WEATHER["icon_center"][1] + WEATHER["range_out"]
    return middle, middle - RANGE_GLYPHS["0"][1] / 2


def weather_range(scene, sample=None):
    """The day's low temperature left of the weather icon and its high
    right of it (see WEATHER's `range`), smaller than the temperature and
    gray, each with a degree sign, along an arc about the face center
    through the icon's middle, following the top of the screen; nothing
    without weather data. Hidden in always-on mode. sample is fixed weather
    to show instead (see TEST_WEATHER), for the test build."""
    def w(source):
        """The expression for a weather data source, or its sample value."""
        return str(sample[source]) if sample else f"[WEATHER.{source}]"

    middle, baseline = range_arc()
    h = RANGE_GLYPHS["0"][1]
    # Where each one stops short of the icon, and each one's arc, in
    # degrees clockwise from 12 (at the baseline, where the text is laid).
    inner = math.degrees((WEATHER_ICON["size"] / 2 + WEATHER["range_gap"]) / middle)
    span = math.degrees(WEATHER["range_width"] / baseline)
    # The degree sign's image ends in the font's spacing, so the low's arc
    # reaches past its ink by that.
    trailing = math.degrees(GAUGE_FONT["tracking"] * WEATHER["range"] * WEATHER["degree"]
                            / baseline)
    group = el(scene, "Group", name="weatherRange", x=0, y=0, width=SIZE, height=SIZE)
    ambient_hide(group)
    shown = el(group, "Condition")
    el(el(shown, "Expressions"), "Expression", name="available").text = w("IS_AVAILABLE")
    branch = el(shown, "Compare", expression="available")
    # Today's forecast low and high (the forecast's first day), in whole
    # degrees: the watch leaves the current conditions' own low and high
    # empty, and a template with an empty value draws nothing.
    for source, start, align in (("DAYS.0.TEMPERATURE_LOW", -inner + trailing - span, "END"),
                                 ("DAYS.0.TEMPERATURE_HIGH", inner, "START")):
        part = el(branch, "PartText", x=0, y=0, width=SIZE, height=SIZE)
        t = el(part, "TextCircular", centerX=C, centerY=C, width=2 * baseline,
               height=2 * baseline, startAngle=fmt(start), endAngle=fmt(start + span),
               direction="CLOCKWISE", align=align)
        template(el(t, "BitmapFont", family="weather_range", size=h), "%s°",
                 f"round({w(source)})")


def clock_box():
    """The time's box on the face at its widest (four of its widest digit
    and the colon), centered on the face: (x, y, width, height) of its ink
    in watch face units, without the spacing after its last character."""
    th = TIME_GLYPHS["0"][1]
    widest = max(TIME_GLYPHS[d][0] for d in SECONDS_CHARS)
    w = 4 * widest + TIME_GLYPHS[":"][0] - GAUGE_FONT["tracking"] * CLOCK["height"]
    return C - w / 2, C - th / 2, w, th


def digital_clock(scene, time=None):
    """The time and its seconds below it (see CLOCK), from the watch's
    clock, each centered on the face; time is a fixed (hour, minute,
    second) to show instead, for the test build. The time stays in
    always-on mode; the seconds are hidden there."""
    _, top, _, th = clock_box()
    sh = SECONDS_GLYPHS["0"][1]
    for name, family, y, h, height, fmt_, fixed, ambient in (
            ("time", "time_digits", top, th, CLOCK["height"], "h:mm",
             time and f'"{(time[0] - 1) % 12 + 1}:{time[1]:02d}"', True),
            ("seconds", "seconds_digits", top + th + CLOCK["seconds_gap"], sh,
             CLOCK["seconds"], "ss", time and f'"{time[2]:02d}"', False)):
        # Each character image ends in the font's spacing, so the box moves
        # right by it to center the ink.
        shift = round(GAUGE_FONT["tracking"] * height)
        if time is None:
            clock = el(scene, "DigitalClock", x=0, y=round(y) - 1, width=SIZE, height=h + 2)
            if not ambient:
                ambient_hide(clock)
            # The time in the chosen color; the seconds stay orange.
            t = el(clock, "TimeText", format=fmt_, align="CENTER", x=shift, y=0,
                   width=SIZE - shift, height=h + 2,
                   **({"tintColor": VALUE_TINT} if name == "time" else {}))
            el(t, "BitmapFont", family=family, size=h)
        else:
            group = el(scene, "Group", name=name, x=0, y=0, width=SIZE, height=SIZE)
            if not ambient:
                ambient_hide(group)
            t = bitmap_text_part(group, y, SIZE - shift, h, x=shift, tint=name == "time")
            template(el(t, "BitmapFont", family=family, size=h), "%s", fixed)


def battery_hours(scene, sample=None):
    """The battery's hours left (see BATTERY_HOURS) centered above the
    time: DataDial Stats' text (red below `low` hours), or "--" without it,
    with the small battery
    centered above it. Its complication slot goes straight in the scene
    (see gauge_complication), after the gauges' (see GAUGES), and covers
    the "--" under it when it has data. Hidden in always-on mode. sample is
    the complication text to show instead (an expression), for the test
    build, which has no complication slot."""
    iw, ih = GAUGE_IMAGES["battery_small"]
    th = BATTERY_HOURS_GLYPHS["0"][1]
    _, clock_top, _, _ = clock_box()
    text_top = clock_top - BATTERY_HOURS["gap"] - th
    icon_top = text_top - BATTERY_HOURS["icon_gap"] - ih
    # Room for five characters ("100h" and more).
    width = math.ceil(5 * max(w for w, _ in BATTERY_HOURS_GLYPHS.values()))
    y0 = math.floor(icon_top) - 1
    b = dict(x=round(C - width / 2), y=y0, width=width,
             height=math.ceil(text_top + th) + 2 - y0)
    # Each character image ends in the font's spacing, so the text's box
    # moves right by half of it to center the ink.
    shift = round(GAUGE_FONT["tracking"] * BATTERY_HOURS["height"] / 2)

    # The "--" under the slot, which a reading covers: its ink's box, with a
    # pixel to spare (the battery is the same in both, so it needs none).
    dash_w = 2 * BATTERY_HOURS_GLYPHS["-"][0] + 2
    dash = dict(x=round(C - dash_w / 2) - b["x"], y=math.floor(text_top) - 1 - y0,
                width=dash_w, height=th + 2)

    def line(parent, text, cover=False, family="battery_hours_digits"):
        """The battery and `text` under parent, with `cover` on black where
        the "--" under it is."""
        if cover:
            draw = el(parent, "PartDraw", **dash)
            el(el(draw, "Rectangle", x=0, y=0, width=dash["width"], height=dash["height"]),
               "Fill", color="#000000")
        icon = el(parent, "PartImage", x=round(C - iw / 2) - b["x"], y=round(icon_top) - y0,
                  width=iw, height=ih)
        el(icon, "Image", resource="battery_small")
        t = bitmap_text_part(parent, text_top - y0, width - shift, th, x=shift,
                             tint=family == "battery_hours_digits")
        template(el(t, "BitmapFont", family=family, size=th), "%s", text)

    group = el(scene, "Group", name="batteryHours", **b)
    ambient_hide(group)
    if sample is not None:
        line(group, sample)
        return
    line(group, '"--"')
    slot = el(scene, "ComplicationSlot", **b, slotId=4, name="battery_timeSlot",
              supportedTypes="SHORT_TEXT EMPTY", isCustomizable="FALSE")
    ambient_hide(slot)
    el(slot, "DefaultProviderPolicy", defaultSystemProvider="EMPTY",
       defaultSystemProviderType="EMPTY", primaryProvider=DATADIAL_BATTERY_TIME,
       primaryProviderType="SHORT_TEXT")
    el(slot, "BoundingBox", x=0, y=0, width=b["width"], height=b["height"])
    # The hours ("7h") in red below the low limit: the text without its
    # "h", through clamp() to make it a number (see text_number).
    text = "[COMPLICATION.TEXT]"
    hours = f"clamp(subText({text}, 0, textLength({text}) - 1), 0, 9999)"
    warn = el(el(slot, "Complication", type="SHORT_TEXT"), "Condition")
    el(el(warn, "Expressions"), "Expression", name="low").text = (
        f"textLength({text}) > 1 && {hours} < {BATTERY_HOURS['low']}")
    line(el(warn, "Compare", expression="low"), text, cover=True,
         family="battery_hours_low_digits")
    line(el(warn, "Default"), text, cover=True)
    line(el(slot, "Complication", type="EMPTY"), '"--"', cover=True)


def watch_face(test=False):
    face = ET.Element("WatchFace", width=str(SIZE), height=str(SIZE))
    el(face, "Metadata", key="CLOCK_TYPE", value="DIGITAL")
    # The picker preview's time (the same as the test build).
    h, m, s = TEST_TIME
    el(face, "Metadata", key="PREVIEW_TIME", value=f"{h:02d}:{m:02d}:{s:02d}")
    user_configurations(face)
    bitmap_fonts(face)
    scene = el(face, "Scene", backgroundColor="#000000")
    weather(scene, sample=TEST_WEATHER if test else None)
    weather_range(scene, sample=TEST_WEATHER if test else None)
    heart_rate(scene, sample=TEST_SOURCES if test else None)
    if DAY_DATE["shown"]:
        day_date(scene, sample=TEST_SOURCES if test else None)
    date_line(scene, sample=TEST_SOURCES if test else None)
    uv_index(scene, sample=TEST_WEATHER if test else None)
    for spec in GAUGES:
        gauge(scene, spec, sample=TEST_SOURCES if test else None)
    battery_hours(scene, sample='"23h"' if test else None)
    digital_clock(scene, time=TEST_TIME if test else None)
    return face


# ------------------------------------------------------------------- images

#: Pixels per watch face unit in the images. Keep it at 1, about the
#: screen's own size: the runtime rotates the hands with bilinear filtering
#: and no mipmaps, so a larger image shrunk on the way skips pixels and its
#: edges come out wavy (at 4, the insert's edge wandered by 0.8 px).
SCALE = 1
#: Pixels per unit the hands are drawn at, for smooth edges. Each hand is
#: drawn once at this size, scaled down to a master image at MASTER_SCALE
#: (written to build/masters/ for review) and from there to SCALE.
DRAW_SCALE = 32
MASTER_SCALE = 8
MASTERS = ROOT / "build" / "masters"
#: Each hand image's width, and its height above and below the dial center,
#: in watch face units (set by HandCanvas).
HAND_IMAGES = {}


def rgb(color):
    """(r, g, b, 255) for a #RRGGBB color."""
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5)) + (255,)


class HandCanvas:
    """A supersampled image of a hand pointing up, the dial center `top`
    units below its top edge, sized to the hand's outline. Points are
    (distance, half-width) as in GAUGE's `pointer`."""

    def __init__(self, name, hand):
        self.name = name
        self.ln = hand["length"] * R
        shape = hand["outline"]
        # Even width, so the image centers on the dial.
        self.w = 2 * math.ceil(max(hw for _, hw in shape) + 1)
        self.top = math.ceil(max(d for d, _ in shape) * self.ln + 1)
        self.bottom = math.ceil(max(0.0, -min(d for d, _ in shape)) * self.ln + 1)
        HAND_IMAGES[name] = (self.w, self.top, self.bottom)
        self.k = DRAW_SCALE
        self.img = Image.new("RGBA", (self.w * self.k, (self.top + self.bottom) * self.k),
                             (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.img)

    def y(self, d):
        """Image row of a distance along the hand."""
        return (self.top - d * self.ln) * self.k

    def polygon(self, points):
        """The closed outline of mirrored (distance, half-width) points."""
        cx, k = self.w * self.k / 2, self.k
        left = [(cx - hw * k, self.y(d)) for d, hw in points]
        right = [(cx + hw * k, self.y(d)) for d, hw in reversed(points) if hw > 0]
        return left + right

    def pixels(self, points):
        """Image coordinates of (x, y) points in watch face units, x across
        the hand from its center line and y along it from the dial center."""
        cx, k = self.w * self.k / 2, self.k
        return [(cx + x * k, (self.top - y) * k) for x, y in points]

    def save(self):
        """Scale down to the master image and from it to the watch's."""
        h = self.top + self.bottom
        master = self.img.resize((self.w * MASTER_SCALE, h * MASTER_SCALE), Image.LANCZOS)
        MASTERS.mkdir(parents=True, exist_ok=True)
        master.save(MASTERS / f"{self.name}.png")
        master.resize((self.w * SCALE, h * SCALE), Image.LANCZOS).save(
            DRAWABLE / f"{self.name}.png")


def render_glyphs(text, height, color=ORANGE):
    """Each character of text as an image `height` pixels tall, in the hour
    numerals' style (see NUMERALS), all on the same baseline: Varela Round
    thickened and narrowed, each "1" a bar with round ends, "-" a short bar
    and "°" a small ring at the top. In `color` (#RRGGBB)."""
    stroke = NUMERALS["stroke"] * height
    color = rgb(color)
    # The font's own stem width, from a lowercase l, to thicken by.
    probe = ImageFont.truetype(str(NUMERAL_FONT), 1000)
    box = probe.getbbox("0")
    size = 1000 * height / (box[3] - box[1])
    font = ImageFont.truetype(str(NUMERAL_FONT), round(size))
    lb = font.getbbox("l")
    stem_img = Image.new("L", (lb[2] + 4, lb[3] + 4), 0)
    ImageDraw.Draw(stem_img).text((0, 0), "l", font=font, fill=255)
    row = [stem_img.getpixel((x, (lb[1] + lb[3]) // 2)) for x in range(stem_img.width)]
    stem = sum(row) / 255
    # Thick enough that the upright strokes keep the stroke width once the
    # digits are narrowed.
    grow = max(0, round((stroke / NUMERALS["condense"] - stem) / 2))
    # Smaller so the thickened digits still come out `height` tall.
    font = ImageFont.truetype(str(NUMERAL_FONT), round(size * height / (height + 2 * grow)))

    # Every digit on the same baseline, the label as tall as a "0"; a "1"
    # as tall as a flat-topped "7".
    top, bottom = font.getbbox("0", stroke_width=grow)[1::2]
    flat = font.getbbox("7", stroke_width=grow)
    glyphs = []
    for ch in text:
        if ch == "1":
            g = Image.new("RGBA", (math.ceil(stroke), bottom - top), (0, 0, 0, 0))
            ImageDraw.Draw(g).rounded_rectangle(
                [0, flat[1] - top, g.width - 1, flat[3] - top - 1], radius=stroke / 2,
                fill=color)
        elif ch == "-":
            g = Image.new("RGBA", (math.ceil(0.45 * height), bottom - top), (0, 0, 0, 0))
            mid = (flat[1] + flat[3]) / 2 - top
            ImageDraw.Draw(g).rounded_rectangle(
                [0, mid - stroke / 2, g.width - 1, mid + stroke / 2], radius=stroke / 2,
                fill=color)
        elif ch == "°":
            ring = 0.40 * height
            g = Image.new("RGBA", (math.ceil(ring), bottom - top), (0, 0, 0, 0))
            y = flat[1] - top
            ImageDraw.Draw(g).ellipse([0, y, ring - 1, y + ring - 1], outline=color,
                                      width=round(0.75 * stroke))
        elif ch == "%":
            # A little taller than the digits: drawn whole, then shrunk to
            # their height.
            b = font.getbbox(ch, stroke_width=grow)
            g = Image.new("RGBA", (b[2] - b[0], b[3] - b[1]), (0, 0, 0, 0))
            ImageDraw.Draw(g).text((-b[0], -b[1]), ch, font=font, fill=color,
                                   stroke_width=grow, stroke_fill=color)
            k = (bottom - top) / g.height
            g = g.resize((round(g.width * k * NUMERALS["condense"]), bottom - top),
                         Image.LANCZOS)
        else:
            b = font.getbbox(ch, stroke_width=grow)
            g = Image.new("RGBA", (b[2] - b[0], bottom - top), (0, 0, 0, 0))
            ImageDraw.Draw(g).text((-b[0], -top), ch, font=font, fill=color,
                                   stroke_width=grow, stroke_fill=color)
            g = g.resize((round(g.width * NUMERALS["condense"]), g.height), Image.LANCZOS)
        glyphs.append(g)
    return glyphs


def render_label(text, k, height=None, color=ORANGE):
    """An hour numeral's image at k pixels per unit, `height` units tall
    (NUMERALS["height"] by default), in `color` (see render_glyphs)."""
    height = (height or NUMERALS["height"]) * k
    glyphs = render_glyphs(text, height, color)
    top, bottom = 0, glyphs[0].height
    gap = round(NUMERALS["tracking"] * height)
    out = Image.new("RGBA", (sum(g.width for g in glyphs) + gap * (len(glyphs) - 1),
                             bottom - top), (0, 0, 0, 0))
    x = 0
    for g in glyphs:
        out.alpha_composite(g, (x, 0))
        x += g.width + gap
    return out


#: Each hour numeral's center and size on the face, (x, y, width, height)
#: in watch face units (set by measure_numerals).
NUMERAL_BOXES = {}


def measure_numerals():
    """Where each hour numeral would sit (see NUMERALS), upright, its outer
    edge NUMERALS["reach"] from the center: NUMERAL_BOXES. Nothing is
    drawn."""
    for hour in range(1, 13):
        label = render_label(str(hour), DRAW_SCALE)
        w, h = label.width / DRAW_SCALE, label.height / DRAW_SCALE
        a = math.radians(hour * 30)
        reach = abs(w / 2 * math.sin(a)) + abs(h / 2 * math.cos(a))
        x, y = polar(hour * 30, NUMERALS["reach"] - reach)
        NUMERAL_BOXES[hour] = (x, y, w, h)


# ------------------------------------------------------------- weather icons

#: Weather icons: orange, in the style of the reference sun (a solid disc
#: with thin rays, long and short). Their size in watch face units, and the
#: width of their thin lines as a fraction of the icon's half-size.
WEATHER_ICON = dict(size=46.0, line=0.075)

#: The weather display, at the top, between the top gauges: the
#: condition's icon at the very top, centered on `icon_center` (small
#: enough to fit inside the round screen there), and the temperature
#: below it, its digits (not the degree sign) centered on `text_center`,
#: the icon orange and the
#: temperature in the readings' color, with a small degree sign and no
#: unit (the watch's own setting). The temperature's digit height (in the
#: gauges' value font), its box width, in watch face units, and the degree
#: sign's size as a fraction of the digits'. Hidden when the watch has no
#: weather; hidden in always-on mode. The day's low and high beside the
#: icon, along the top of the screen (see weather_range): their digit
#: height, their gap from the icon, each one's room along the arc, and how
#: far their arc is outside the icon's middle (toward the screen's edge),
#: in watch face units, and their light gray.
WEATHER = dict(icon_center=(225.0, 29.0), text_center=(225.0, 74.0), temperature=32.0,
               text_width=110.0, degree=0.6, range=16.0, range_gap=15.0, range_width=50.0, range_out=10.0,
               range_color="#B4B4B4")
#: The icon for each [WEATHER.CONDITION] value, 0 to 15, by day and by night.
WEATHER_CONDITIONS = (
    ("unknown", "unknown"), ("clear_day", "clear_night"), ("cloudy", "cloudy"),
    ("fog", "fog"), ("heavy_rain", "heavy_rain"), ("heavy_snow", "heavy_snow"),
    ("rain", "rain"), ("snow", "snow"), ("clear_day", "clear_night"),  # 8: sunny
    ("thunderstorm", "thunderstorm"), ("sleet", "sleet"), ("light_snow", "light_snow"),
    ("light_rain", "light_rain"), ("mist", "mist"),
    ("partly_cloudy_day", "partly_cloudy_night"), ("windy", "windy"),
)
#: The temperature's characters and their image names.
TEMPERATURE_CHARS = {**{str(n): str(n) for n in range(10)},
                     "-": "minus", "°": "degree"}
#: Each temperature character's image size in pixels, and the low and
#: high's (set by render_temperature_glyphs).
TEMPERATURE_GLYPHS = {}
RANGE_GLYPHS = {}
#: The temperature's colors: red above the hot limit, blue below the cold
#: one, the readings' gray between (limits in °F; converted when the watch
#: uses °C).
#: Each color is its own image font: "weather_temperature", then "_hot"
#: and "_cold".
TEMPERATURE_COLORS = {"": VALUE_COLOR, "hot": "#FF3B30", "cold": "#3D8BFF"}
TEMPERATURE_LIMITS = dict(hot=90, cold=40)


def temperature_set(key):
    """The image name suffix of a TEMPERATURE_COLORS set: "" or "_hot"."""
    return f"_{key}" if key else ""


class Icon:
    """A weather icon drawn as a grayscale mask, in icon coordinates: -1 to
    1 across and down, the icon's center at 0."""

    def __init__(self):
        self.n = round(WEATHER_ICON["size"] * DRAW_SCALE)
        self.mask = Image.new("L", (self.n, self.n), 0)
        self.draw = ImageDraw.Draw(self.mask)
        self.w = WEATHER_ICON["line"]

    def px(self, x, y):
        return (x + 1) / 2 * self.n, (y + 1) / 2 * self.n

    def size(self, v):
        return v / 2 * self.n

    def disc(self, x, y, r, fill=255):
        (cx, cy), r = self.px(x, y), self.size(r)
        self.draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)

    def line(self, x0, y0, x1, y1, width=None, fill=255):
        """A straight line with round ends."""
        width = width or self.w
        self.draw.line([self.px(x0, y0), self.px(x1, y1)], fill=fill,
                       width=round(self.size(width)))
        for x, y in ((x0, y0), (x1, y1)):
            self.disc(x, y, width / 2, fill)

    def polygon(self, points, fill=255):
        self.draw.polygon([self.px(x, y) for x, y in points], fill=fill)

    def sun(self, x, y, k):
        """The reference sun: a disc and 16 rays, long and short."""
        self.disc(x, y, 0.39 * k)
        for i in range(16):
            a = math.radians(i * 22.5)
            outer = (1.0 if i % 2 == 0 else 0.80) * k
            self.line(x + 0.55 * k * math.sin(a), y - 0.55 * k * math.cos(a),
                      x + outer * math.sin(a), y - outer * math.cos(a))

    def moon(self, x, y, k):
        """A crescent: a disc with an offset disc cut out of it."""
        self.disc(x, y, 0.62 * k)
        self.disc(x + 0.36 * k, y - 0.26 * k, 0.52 * k, fill=0)

    def cloud(self, x, y, k, grow=0.0, fill=255):
        """A cloud: three puffs on a flat-bottomed base. grow widens it on
        every side (for the gap around it)."""
        for cx, cy, r in ((-0.42, 0.10, 0.30), (0.05, -0.12, 0.40), (0.45, 0.12, 0.27)):
            self.disc(x + cx * k, y + cy * k, r * k + grow, fill)
        x0, y0 = self.px(x - 0.72 * k - grow, y - 0.0 * k - grow)
        x1, y1 = self.px(x + 0.72 * k + grow, y + 0.40 * k + grow)
        self.draw.rounded_rectangle([x0, y0, x1, y1], radius=self.size(0.2 * k + grow),
                                    fill=fill)

    def cloud_over(self, x, y, k):
        """A cloud in front of what's already drawn, with a gap around it."""
        self.cloud(x, y, k, grow=self.w * 1.2, fill=0)
        self.cloud(x, y, k)

    def flake(self, x, y, r):
        """A small six-armed snowflake."""
        for i in range(3):
            a = math.radians(i * 60)
            dx, dy = r * math.cos(a), r * math.sin(a)
            self.line(x - dx, y - dy, x + dx, y + dy, width=self.w * 0.9)

    def drops(self, xs, y0, y1):
        """Slanted rain lines under a cloud."""
        for x in xs:
            self.line(x, y0, x - 0.12 * (y1 - y0) / 0.34, y1, width=self.w * 1.2)

    def wind(self, y, x0, x1, r):
        """A wind line ending in a curl."""
        self.line(x0, y, x1, y)
        (cx, cy), rr = self.px(x1, y - r), self.size(r)
        w = round(self.size(self.w))
        self.draw.arc([cx - rr, cy - rr, cx + rr, cy + rr], start=180, end=90, fill=255,
                      width=w)
        self.disc(x1 - r, y - r, self.w / 2)


def weather_icons():
    """The weather icons by name: functions drawing each on an Icon."""
    def clear_day(i): i.sun(0, 0, 0.95)
    def clear_night(i): i.moon(-0.05, 0.05, 1.3)

    def partly_cloudy_day(i):
        i.sun(-0.28, -0.30, 0.62)
        i.cloud_over(0.12, 0.22, 0.85)

    def partly_cloudy_night(i):
        i.moon(-0.30, -0.32, 0.85)
        i.cloud_over(0.12, 0.22, 0.85)

    def cloudy(i):
        i.cloud(0.24, -0.45, 0.62)
        i.cloud_over(-0.08, 0.12, 1.0)

    def precip(i, rain=(), flakes=(), long=False):
        i.cloud(0, -0.28, 0.95)
        if rain:
            i.drops(rain, 0.30, 0.80 if long else 0.62)
        for x, y in flakes:
            i.flake(x, y, 0.13)

    def light_rain(i): precip(i, rain=(-0.15, 0.25))
    def rain(i): precip(i, rain=(-0.35, 0.05, 0.45))
    def heavy_rain(i): precip(i, rain=(-0.50, -0.20, 0.10, 0.40, 0.70), long=True)
    def light_snow(i): precip(i, flakes=((-0.25, 0.52), (0.30, 0.60)))
    def snow(i): precip(i, flakes=((-0.45, 0.50), (0.05, 0.72), (0.50, 0.50)))

    def heavy_snow(i):
        precip(i, flakes=((-0.55, 0.45), (-0.15, 0.62), (0.25, 0.45), (0.62, 0.62),
                          (0.05, 0.88)))

    def sleet(i):
        precip(i, rain=(-0.52, 0.25))
        i.flake(-0.16, 0.60, 0.13)
        i.flake(0.60, 0.60, 0.13)

    def thunderstorm(i):
        i.cloud(0, -0.30, 0.95)
        i.polygon([(0.08, 0.20), (-0.20, 0.60), (0.0, 0.60), (-0.14, 0.95), (0.28, 0.48),
                   (0.07, 0.48), (0.24, 0.20)])

    def fog(i):
        i.cloud(0, -0.35, 0.85)
        for y, x0, x1 in ((0.30, -0.70, 0.70), (0.55, -0.85, 0.55), (0.80, -0.55, 0.85)):
            i.line(x0, y, x1, y, width=i.w * 1.3)

    def mist(i):
        for row, y in enumerate((-0.45, -0.15, 0.15, 0.45)):
            x = -0.85 + (0.18 if row % 2 else 0)
            while x < 0.80:
                i.line(x, y, min(x + 0.42, 0.85), y, width=i.w * 1.3)
                x += 0.62

    def windy(i):
        i.wind(-0.35, -0.85, 0.35, 0.22)
        i.wind(0.05, -0.85, 0.60, 0.20)
        i.wind(0.45, -0.85, 0.15, 0.18)

    def unknown(i):
        font = ImageFont.truetype(str(NUMERAL_FONT), round(i.n * 0.95))
        b = i.draw.textbbox((0, 0), "?", font=font)
        i.draw.text(((i.n - b[2] - b[0]) / 2, (i.n - b[3] - b[1]) / 2), "?", font=font,
                    fill=255)

    return dict(unknown=unknown, clear_day=clear_day, clear_night=clear_night,
                partly_cloudy_day=partly_cloudy_day, partly_cloudy_night=partly_cloudy_night,
                cloudy=cloudy, fog=fog, mist=mist, light_rain=light_rain, rain=rain,
                heavy_rain=heavy_rain, light_snow=light_snow, snow=snow,
                heavy_snow=heavy_snow, sleet=sleet, thunderstorm=thunderstorm, windy=windy)


def render_weather_icons():
    """Each weather icon in orange, as a master and at screen size, and a
    sheet of all of them for review (build/masters/weather_icons.png)."""
    masters = {}
    for name, paint in weather_icons().items():
        icon = Icon()
        paint(icon)
        img = Image.new("RGBA", icon.mask.size, rgb(ORANGE))
        img.putalpha(icon.mask)
        size = WEATHER_ICON["size"]
        master = img.resize((round(size * MASTER_SCALE),) * 2, Image.LANCZOS)
        masters[name] = master
        MASTERS.mkdir(parents=True, exist_ok=True)
        master.save(MASTERS / f"weather_{name}.png")
        master.resize((round(size * SCALE),) * 2, Image.LANCZOS).save(
            DRAWABLE / f"weather_{name}.png")
    # The review sheet: every icon with its name, on black.
    cell = round(WEATHER_ICON["size"] * MASTER_SCALE)
    cols = 6
    rows = math.ceil(len(masters) / cols)
    label = ImageFont.truetype(str(NUMERAL_FONT), cell // 9)
    sheet = Image.new("RGBA", (cols * (cell + 40), rows * (cell + 80)), (0, 0, 0, 255))
    draw = ImageDraw.Draw(sheet)
    for n, (name, img) in enumerate(masters.items()):
        x, y = (n % cols) * (cell + 40) + 20, (n // cols) * (cell + 80) + 20
        sheet.alpha_composite(img, (x, y))
        draw.text((x + cell / 2, y + cell + 30), name.replace("_", " "), font=label,
                  fill=(160, 160, 160, 255), anchor="mm")
    sheet.convert("RGB").save(MASTERS / "weather_icons.png")


#: The heart rate's and the UV index's characters, and each one's image
#: size in pixels (set by render_heart_rate_glyphs; the same in every
#: color).
HEART_RATE_CHARS = {**{str(n): str(n) for n in range(10)}, "-": "minus"}
HEART_RATE_GLYPHS = {}
#: The heart rate's own characters' image sizes (set by
#: render_heart_rate_glyphs).
HR_GLYPHS = {}


def readout_sets():
    """The readouts' digit sets, name to color: the heart rate's gray
    ("heart_rate", also the UV's "--") and one per UV level ("uv_low" ...)."""
    return {"heart_rate": VALUE_COLOR, **{f"uv_{name}": color for name, _, color in UV_LEVELS}}


def render_value_glyph(ch, height, color, file, trailing=True, tight=False):
    """One character of a reading in the gauges' value font (GAUGE_FONT at
    the values' weight, as under the gauges' needles), `height` units tall
    and in `color`, with the font's spacing after it when `trailing`: the
    master, and the watch's image drawn straight at its pixel size (crisp)
    as <file>.png. With `tight`, the image is cut to the character's ink
    and the font's spacing follows it, so text of these characters is as
    wide as its ink plus that spacing, and centering it centers its ink
    (a font's side bearings differ from character to character: a "1"
    has more room on its left). Returns the master and the watch image's
    size."""
    weight = GAUGE["value"]["weight"]
    images = []
    for scale in (MASTER_SCALE, SCALE):
        img = render_gauge_text(ch, height * scale, color, trailing and not tight, weight)
        ink = img.getchannel("A").getbbox()
        if tight and ink:
            gap = round(GAUGE_FONT["tracking"] * height * scale) if trailing else 0
            cut = Image.new("RGBA", (ink[2] - ink[0] + gap, img.height), (0, 0, 0, 0))
            cut.alpha_composite(img.crop((ink[0], 0, ink[2], img.height)))
            img = cut
        images.append(img)
    master, img = images
    master.save(MASTERS / f"{file}.png")
    img.save(DRAWABLE / f"{file}.png")
    return master, img.size


def render_heart_rate_glyphs():
    """The UV index's characters in the gauges' value font, HEART_RATE's
    UV digit height, a set per readout_sets() color: <set>_<name>.png; and
    the heart rate's, at its own height, gray: hr_<name>.png."""
    for prefix, color in readout_sets().items():
        for ch, name in HEART_RATE_CHARS.items():
            _, size = render_value_glyph(ch, HEART_RATE["digits"], color, f"{prefix}_{name}",
                                         tight=True)
            HEART_RATE_GLYPHS[ch] = size
    for ch, name in HEART_RATE_CHARS.items():
        _, HR_GLYPHS[ch] = render_value_glyph(ch, HEART_RATE["value"], VALUE_COLOR, f"hr_{name}",
                                              tight=True)


def render_temperature_set(prefix, height, color, glyphs):
    """One set of temperature characters (TEMPERATURE_CHARS) in the values'
    font, `height` units tall and in `color`: <prefix>_<name>.png, each
    one's size in `glyphs`; the degree sign smaller (WEATHER's `degree`),
    level with the digits' tops, in an image as tall as theirs."""
    for ch, name in TEMPERATURE_CHARS.items():
        file = f"{prefix}_{name}"
        if ch != "°":
            _, glyphs[name] = render_value_glyph(ch, height, color, file, tight=True)
            continue
        weight = GAUGE["value"]["weight"]
        for scale, folder in ((MASTER_SCALE, MASTERS), (SCALE, DRAWABLE)):
            full = render_gauge_text("0", height * scale, color, True, weight)
            # The sign by its own ink, its top at the digits' tops: a font's
            # degree sign can sit above its capitals, where an image cut at
            # their top would clip it.
            small = height * WEATHER["degree"] * scale
            font, _, _ = gauge_font(small, weight=weight)
            left, top, right, bottom = font.getbbox(ch, anchor="ls")
            ring = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
            ImageDraw.Draw(ring).text((-left, -top), ch, font=font, fill=rgb(color),
                                      anchor="ls")
            gap = GAUGE_FONT["tracking"] * small
            img = Image.new("RGBA", (math.ceil(ring.width + gap), full.height), (0, 0, 0, 0))
            img.alpha_composite(ring)
            img.save(folder / f"{file}.png")
        glyphs[name] = img.size


def render_temperature_glyphs():
    """The temperature's characters, a set per TEMPERATURE_COLORS color:
    weather_temp<set>_<name>.png; and the day's low and high, smaller and
    gray: weather_range_<name>.png (see render_temperature_set)."""
    for key, color in TEMPERATURE_COLORS.items():
        render_temperature_set(f"weather_temp{temperature_set(key)}", WEATHER["temperature"],
                               color, TEMPERATURE_GLYPHS)
    render_temperature_set("weather_range", WEATHER["range"], WEATHER["range_color"],
                           RANGE_GLYPHS)


# ------------------------------------------------------------------- battery

#: The battery gauge's icon: an orange battery outline with a terminal nub
#: on the right and a row of segments inside, one per 20%. In watch face
#: units: the body's width and height, its outline's width and corner
#: radius, the nub's width and height, the space between the outline and
#: the segments, and the gaps between segments; and the battery-time
#: ring's small battery's size as a fraction of it.
BATTERY = dict(body=(38.0, 18.0), line=2.2, radius=4.0, nub=(3.2, 7.2), pad=1.8,
               segments=5, segment_gap=1.6, small=0.55)
#: Below this percentage the battery icon is red (the hot temperature's
#: red): the "_low" images.
BATTERY_LOW = dict(limit=20, color=TEMPERATURE_COLORS["hot"])
#: The battery icon's size in pixels (set by render_battery).
BATTERY_IMAGES = {}


def render_battery_icon(filled, low=False, scale=1.0, name=None):
    """The battery with `filled` of its segments lit (left first), drawn
    large, as a master image and at screen size: battery_<filled>.png, or
    battery_low_<filled>.png in the low battery's red; or, at `scale`
    times BATTERY's size, <name>.png. Returns the master and the screen
    image's size."""
    k = DRAW_SCALE
    (bw, bh), line = (scale * v for v in BATTERY["body"]), scale * BATTERY["line"]
    nw, nh = (scale * v for v in BATTERY["nub"])
    margin = 1.0
    w, h = math.ceil(bw + nw + 2 * margin), math.ceil(bh + 2 * margin)
    img = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = rgb(BATTERY_LOW["color"] if low else ORANGE)
    name = name or f"battery{'_low' if low else ''}_{filled}"
    x0, y0 = (w - bw - nw) / 2, (h - bh) / 2
    draw.rounded_rectangle([x0 * k, y0 * k, (x0 + bw) * k, (y0 + bh) * k],
                           radius=scale * BATTERY["radius"] * k, outline=color,
                           width=round(line * k))
    # The nub, from under the outline's right side out, its outer corners round.
    ny = y0 + (bh - nh) / 2
    draw.rounded_rectangle([(x0 + bw - line) * k, ny * k, (x0 + bw + nw) * k, (ny + nh) * k],
                           radius=nw * 0.55 * k, fill=color, corners=(False, True, True, False))
    # The segments, evenly across the inside.
    n, gap, pad = BATTERY["segments"], scale * BATTERY["segment_gap"], scale * BATTERY["pad"]
    ix, iy = x0 + line + pad, y0 + line + pad
    iw, ih = bw - 2 * (line + pad), bh - 2 * (line + pad)
    sw = (iw - gap * (n - 1)) / n
    for i in range(filled):
        sx = ix + i * (sw + gap)
        draw.rounded_rectangle([sx * k, iy * k, (sx + sw) * k, (iy + ih) * k],
                               radius=scale * 0.8 * k, fill=color)
    master = img.resize((w * MASTER_SCALE, h * MASTER_SCALE), Image.LANCZOS)
    MASTERS.mkdir(parents=True, exist_ok=True)
    master.save(MASTERS / f"{name}.png")
    master.resize((w * SCALE, h * SCALE), Image.LANCZOS).save(DRAWABLE / f"{name}.png")
    return master, (w * SCALE, h * SCALE)


def battery_segments(level):
    """How many segments are lit at a percentage: one per step, rounded up."""
    return math.ceil(level * BATTERY["segments"] / 100)


def render_battery():
    """The battery icons, in orange and in the low battery's red, each for
    as many segments as a level in its color can light; and the small one,
    full (battery_small.png)."""
    limit = BATTERY_LOW["limit"]
    for n in range(battery_segments(limit), BATTERY["segments"] + 1):
        _, BATTERY_IMAGES["icon"] = render_battery_icon(n)
    for n in range(battery_segments(limit - 1) + 1):
        render_battery_icon(n, low=True)
    GAUGE_IMAGES["battery"] = BATTERY_IMAGES["icon"]
    # The battery hours' small, full battery (see battery_hours).
    _, GAUGE_IMAGES["battery_small"] = render_battery_icon(
        BATTERY["segments"], scale=BATTERY["small"], name="battery_small")


# -------------------------------------------------------------------- gauges

#: The gauges' shared style, in the reference gauge's colors: a small dial
#: with gray tick marks around an arc open at the bottom, gray labels
#: upright inside them, an orange pointer on a light gray hub, and a gray
#: value below the hub. In watch face units:
#:
#: - distance: each gauge center's distance from the dial center, and
#:   shift: how far each then moves toward the middle row, the top two
#:   down and the bottom two up.
#: - ticks: (inner radius, length, width) of the tick marks.
#: - labels: the labels' capital height, and the gap between each label's
#:   outer edge and the ticks (placed like the hour numerals).
#: - arc: the scale's span in degrees, its low end at the left, unless a
#:   gauge sets its own.
#: - pointer: its outline as (distance, half-width) points down one side,
#:   from the tail to the tip, mirrored for the other side (distances as
#:   fractions of its length, half-widths in watch face units), the
#:   reference's: straight sides widening from the hub to a
#:   shoulder at 0.71 of its length, then straight to a sharp point, its
#:   tail hidden under the hub. It runs over the labels, to `gap` short
#:   of the ticks.
#: - hub: discs as (radius, color), outermost first, each drawn over the
#:   last: light gray rings with a dark one between, as in the reference.
#: - value: the value's digit height, its gap below the hub and its font weight
#:   (regular, also for the readouts' values); and the units' letters ("ft"),
#:   small: their height as a fraction of the digits', centered on them.
#: - unit: the unit label's capital height (beside the hub).
#: - bar: the progress bar along the ring's middle (`ticks` gives the
#:   ring's radius: its inner radius and length), from the scale's low end
#:   to its value, its ends round: its width, and its colors by how far
#:   along the scale it is (below this fraction, color), the last for the
#:   rest: orange all the way.
#: - track: the color of the ring under the bar, the whole scale, as wide
#:   as the bar with round ends (the Pixel Watch Active face's rings).
#: - dot: the marker at the bar's end: a disc (its radius and color) on a
#:   black ring `edge` wide that sets it off from the bar.
#: - redline: for a gauge with a `redline` (its low and high values), a red
#:   band through the middle of its ticks over that stretch, under them,
#:   like an engine's redline: its width and its color.
GAUGE = dict(
    distance=157.0,
    shift=0.0,
    ticks=(56.0, 4.4, 1.8),
    labels=dict(height=12.0, gap=3.0),
    arc=240.0,
    pointer=dict(gap=2.0, outline=((-0.10, 2.35), (0.0, 2.47), (0.71, 3.33), (1.0, 0.0))),
    hub=((6.0, "#DCDCDC"), (4.5, "#161616"), (3.5, "#BEBEBE"), (2.4, "#8E8E8E"),
         (0.8, "#222222")),
    value=dict(height=19.0, gap=2.0, weight=None, unit=0.55),
    unit=7.0,
    redline=dict(width=2.0, color="#FF3B30"),
    bar=dict(width=9.0, colors=((None, ORANGE),)),
    track="#3A3A3A",
    dot=dict(radius=4.0, edge=1.6, color="#FFFFFF"),
)
#: The values' font, for the time, the gauges and every reading: Google
#: Sans Flex (SIL Open Font License, tools/fonts/), the Pixel Watch faces'
#: font, set as on the Pixel Watch's Active face. The font file; its
#: variable axes' settings by name (any left out stay at the font's
#: default): bold, fully rounded, a display optical size; and the space
#: between characters as a fraction of the cap height.
GAUGE_FONT = dict(file=ROOT / "tools" / "fonts" / "GoogleSansFlex.ttf",
                  axes={"Weight": 700, "Roundness": 100, "Optical Size": 36}, tracking=0.04)

#: The gauges. Each has a name (its dial image is <name>_dial.png), its
#: angle on the face (clockwise from 12), its scale's low and high values
#: (and its own arc, if not GAUGE's),
#: the values with tick marks and with labels (value, text), the pointer's
#: expression on that scale (and a big-number gauge's `number`, for its
#: bar and its value's size), the value's expression shown below the hub
#: (and, optionally, an expression that is false when there is no data, to
#: show "--" instead, an icon image below the value, a unit label right of
#: the hub, and a complication), and the pointer and value shown on its
#: review sheet. A gauge with a complication has no watch data source of
#: its own: its slot is filled from another app's complication `provider`
#: (of `provider_type`). Its `source` stands for the number in `pointer`,
#: its `types` give each complication type it takes that type's number
#: and the value shown (with, optionally, an expression false when the
#: fallback, by default "--", shows instead), and `test` the type the test
#: build shows, with `sample`'s values for that type's data sources.
#:
#: - steps, in the 10:30 segment, a big-number gauge (see BIG_VALUE):
#:   today's steps, large, inside a tick every 500 up to 10000 over the
#:   pulse reference's wider arc (its ends at 144 degrees either side of
#:   12), green once they reach the step goal, with its footprints below.
#:   They come from Google Health's steps complication, as on DataDial (a
#:   goal progress value; ranged values and short text also work), "--"
#:   without it.
#: - calories, in the 7:30 segment, a big-number gauge: the day's calories
#:   (without a thousands separator), the bar full at 3000, a tick every
#:   150. Wear OS gives watch faces no calorie count, so they come from
#:   Google Health's complication, as on DataDial (short text, the bar at
#:   its number; a ranged or goal value also works), "--" without it.
#: - elevation, in the 4:30 segment, a big-number gauge: the feet, with
#:   "ft" above, the bar full at 10000 ft, a tick every 500. Wear OS gives watch
#:   faces no elevation, so it comes from DataDial Stats' complication, as
#:   on DataDial, "--" without it.
#: - battery, in the 1:30 segment, a big-number gauge: the watch's battery
#:   percentage with "%" above it (red, as the bar, below BATTERY_LOW's
#:   limit: `low`), a tick every 5%, the bar orange, red
#:   below BATTERY_LOW's limit, and the
#:   battery icon below, a segment lit per 20% (red when low). From the
#:   watch itself: no complication.
#: Google Health's steps on the watch, as DataDial uses them: today's
#: steps toward the step goal, as a goal progress value.
GOOGLE_HEALTH_STEPS = ("com.fitbit.FitbitMobile/"
                       "com.fitbit.complications.offloadable.steps."
                       "OffloadableStepsComplicationDataSourceService")
#: Google Health's calories on the watch (its package is still
#: com.fitbit.FitbitMobile), as DataDial uses them: today's calories,
#: resting ones included, as short text with a thousands separator
#: ("1,850").
GOOGLE_HEALTH_CALORIES = (
    "com.fitbit.FitbitMobile/com.google.android.wearable.fitbit.mainapp.complications"
    ".offloadable.calories.OffloadableCaloriesComplicationDataSourceService")


def text_number(text):
    """An expression for the number in `text`, a whole number under a
    million with or without a thousands separator ("1,850" or "1850"): the
    digits before the separator times 1000 plus the three after it. Text
    can't be used in arithmetic (the result is empty), but clamp() turns
    it into a number, so each piece goes through clamp()."""
    n = f"textLength({text})"

    def number(e):
        return f"clamp({e}, 0, 999999)"
    return (f"({n} > 4 ? {number(f'subText({text}, 0, {n} - 4)')} * 1000 + "
            f"{number(f'subText({text}, {n} - 3, {n})')} : {number(text)})")


#: DataDial Stats' elevation (DataDial's own companion app, as the
#: DataDial watch face uses it): the barometer's elevation as short text,
#: whole feet with "ft" after them ("1234ft"), or "--" without a reading.
#: (Where the watch's region uses metric units it sends meters, "376m",
#: which this face doesn't read.)
DATADIAL_ELEVATION = ("io.github.ls6777.datadial.stats/"
                      "io.github.ls6777.datadial.stats.ElevationSource")


#: DataDial Stats' battery time left ("23h"), from the rate the battery
#: has been draining.
DATADIAL_BATTERY_TIME = ("io.github.ls6777.datadial.stats/"
                         "io.github.ls6777.datadial.stats.BatteryTimeSource")


def elevation_number(text):
    """An expression for the feet in DataDial Stats' elevation `text`
    ("1234ft"): the text without its last two characters, through clamp()
    to make it a number (see text_number); 0 for "--" (too short to hold
    a number and "ft")."""
    n = f"textLength({text})"
    return f"({n} > 2 ? clamp(subText({text}, 0, {n} - 2), -99999, 999999) : 0)"


CALORIE_GAUGE = dict(
    name="calories", angle=-135.0, scale=(0, 3000), arc=288.0,
    ticks=list(range(0, 3001, 150)), labels=[], big=True,
    pointer="clamp([CALORIES], 0, 3000)", icon="gauge_flame",
    complication=dict(
        slot=1, source="[CALORIES]", provider=GOOGLE_HEALTH_CALORIES, provider_type="SHORT_TEXT",
        types={
            # Shown without its thousands separator: from 1000 up, the
            # number read from the text; below that, the text as it is
            # (also "--" without data).
            "SHORT_TEXT": dict(number=text_number("[COMPLICATION.TEXT]"),
                               value=f'round({text_number("[COMPLICATION.TEXT]")})',
                               available="textLength([COMPLICATION.TEXT]) > 3",
                               fallback="[COMPLICATION.TEXT]"),
            "RANGED_VALUE": dict(number="[COMPLICATION.RANGED_VALUE_VALUE]",
                                 value="round([COMPLICATION.RANGED_VALUE_VALUE])"),
            "GOAL_PROGRESS": dict(number="[COMPLICATION.GOAL_PROGRESS_VALUE]",
                                  value="round([COMPLICATION.GOAL_PROGRESS_VALUE])"),
        },
        test="SHORT_TEXT", sample={"[COMPLICATION.TEXT]": '"1,850"'}),
    review=dict(pointer=1850, value="1850"),
)
ELEVATION_GAUGE = dict(
    name="elevation", angle=135.0, scale=(0, 10000), arc=288.0,
    ticks=list(range(0, 10001, 500)), labels=[], big=True, unit_label="ft",
    pointer="clamp([ELEVATION], 0, 10000)", icon="gauge_mountain",
    complication=dict(
        slot=2, source="[ELEVATION]", provider=DATADIAL_ELEVATION, provider_type="SHORT_TEXT",
        types={
            # The feet without their "ft" (shown above them: unit_label), or
            # "--" as it is.
            "SHORT_TEXT": dict(
                number=elevation_number("[COMPLICATION.TEXT]"),
                value="subText([COMPLICATION.TEXT], 0, textLength([COMPLICATION.TEXT]) - 2)",
                available="textLength([COMPLICATION.TEXT]) > 2",
                fallback="[COMPLICATION.TEXT]"),
        },
        test="SHORT_TEXT", sample={"[COMPLICATION.TEXT]": '"8250ft"'}),
    review=dict(pointer=8250, value="8250"),
)
STEPS_GAUGE = dict(
    name="steps", angle=-45.0, scale=(0, 10000), arc=288.0,
    ticks=list(range(0, 10001, 500)), labels=[], big=True,
    pointer="clamp([STEPS], 0, 10000)", icon="gauge_steps",
    complication=dict(
        slot=3, source="[STEPS]", provider=GOOGLE_HEALTH_STEPS, provider_type="GOAL_PROGRESS",
        types={
            # Green once the steps reach the goal (or the range's top).
            "GOAL_PROGRESS": dict(
                number="[COMPLICATION.GOAL_PROGRESS_VALUE]",
                value="round([COMPLICATION.GOAL_PROGRESS_VALUE])",
                goal="[COMPLICATION.GOAL_PROGRESS_TARGET_VALUE] > 0 && "
                     "[COMPLICATION.GOAL_PROGRESS_VALUE] >= "
                     "[COMPLICATION.GOAL_PROGRESS_TARGET_VALUE]"),
            "RANGED_VALUE": dict(
                number="[COMPLICATION.RANGED_VALUE_VALUE]",
                value="round([COMPLICATION.RANGED_VALUE_VALUE])",
                goal="[COMPLICATION.RANGED_VALUE_MAX] > 0 && "
                     "[COMPLICATION.RANGED_VALUE_VALUE] >= [COMPLICATION.RANGED_VALUE_MAX]"),
            # As the calories: without the thousands separator (and no goal).
            "SHORT_TEXT": dict(number=text_number("[COMPLICATION.TEXT]"),
                               value=f'round({text_number("[COMPLICATION.TEXT]")})',
                               available="textLength([COMPLICATION.TEXT]) > 3",
                               fallback="[COMPLICATION.TEXT]"),
        },
        test="GOAL_PROGRESS", sample={"[COMPLICATION.GOAL_PROGRESS_VALUE]": 8250,
                                      "[COMPLICATION.GOAL_PROGRESS_TARGET_VALUE]": 10000}),
    review=dict(pointer=8250, value="8250"),
)
BATTERY_GAUGE = dict(
    name="battery", angle=45.0, scale=(0, 100), arc=288.0,
    ticks=list(range(0, 101, 5)), labels=[], big=True, unit_label="%",
    bar_colors=((BATTERY_LOW["limit"] / 100, BATTERY_LOW["color"]), (None, ORANGE)),
    pointer="clamp([BATTERY_PERCENT], 0, 100)", number="[BATTERY_PERCENT]",
    value="[BATTERY_PERCENT]", low=f"[BATTERY_PERCENT] < {BATTERY_LOW['limit']}",
    icon="battery",
    review=dict(pointer=80, value="80"),
)
#: The gauges, in the order their complication slots were added: the
#: runtime matches a watch's saved slot choices by their order, so a new
#: slot goes last (the battery has none; the battery hours' slot, 4, comes
#: after these: see battery_hours).
GAUGES = (CALORIE_GAUGE, ELEVATION_GAUGE, STEPS_GAUGE, BATTERY_GAUGE)
#: The gap between a gauge's value and its icon, in watch face units.
GAUGE_ICON_GAP = 7.0
#: The day of the week ("WED") above the month and date ("NOV 28"), at the
#: bottom between the bottom gauges, white in the gauges' value font, all
#: one size; the month and date along the bottom of the screen, on an arc
#: about the face center. Their capital height, the month and date's gap
#: above the bottom of the screen, the gap between the lines, and the
#: month and date's room along the arc, in watch face units.
DATE_LINE = dict(height=26.0, bottom=20.0, spacing=11.0, arc_width=140.0)
#: The date lines' characters (digits, a space, and the day and month
#: names' letters), their image names, and each one's image size (set by
#: render_gauges).
DATE_LINE_CHARS = {**{str(n): str(n) for n in range(10)}, " ": "space",
                   **{c: c.lower() for c in "SUNMOTEWDHFRIAJBYLGPCV"}}
DATE_LINE_GLYPHS = {}

#: The digital time in the middle of the face, between the UV index and
#: the heart rate: hours and minutes ("h:mm", 12 or 24 hour as the watch is
#: set) in white, centered on the face, and the seconds centered under
#: them in orange, hidden in always-on mode. The time's capital height, the
#: seconds', and the gap between the two, in watch face units.
CLOCK = dict(height=64.0, seconds=38.0, seconds_gap=7.0, seconds_color=ORANGE)
#: The time's characters and the seconds', their image names, and each
#: one's image size (set by render_clock_glyphs).
TIME_CHARS = {**{str(n): str(n) for n in range(10)}, ":": "colon"}
SECONDS_CHARS = {str(n): str(n) for n in range(10)}
TIME_GLYPHS = {}
SECONDS_GLYPHS = {}

#: The battery's hours left, centered above the time: DataDial Stats'
#: battery time as it sends it ("23h"), or "--" without it, and the small
#: battery centered above it. Wear OS gives watch faces no time left, so
#: it comes from that app's complication (slot 4). Its capital height,
#: its gap above the time, and the battery's gap above it, in watch face
#: units; and the hours below which it is red (BATTERY_LOW's color).
BATTERY_HOURS = dict(height=24.0, gap=21.0, icon_gap=6.0, low=8)
#: The battery hours' characters, their image names, and each one's image
#: size (set by render_clock_glyphs).
BATTERY_HOURS_CHARS = {**{str(n): str(n) for n in range(10)}, "-": "minus", "h": "h"}
BATTERY_HOURS_GLYPHS = {}

#: The day of the week and the date, in the middle, in the gauges' value
#: font, gray: the day's full name right of the hub and level with it,
#: centered between the hub and a two-digit UV index, and the day of the
#: month above the hub, centered between it and the top gauges. The name's
#: capital height, the date's digit height, the date's box width, and how
#: far the name sits right of its midpoint and the date below its, in
#: watch face units; the radius it keeps clear around the center (the old
#: hub's); and whether they're on the face (off for now).
DAY_DATE = dict(hub=11.6, name=13.0, date=24.0, width=100.0, name_right=5.0, date_down=10.0,
                shown=False)
#: The date's digits' image sizes in pixels (set by render_day_names).
DATE_GLYPHS = {}
DAY_NAMES = ("SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY")
#: The months' three letters, January first.
MONTH_NAMES = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV",
               "DEC")
#: Each day name's image size in pixels (set by render_day_names).
DAY_IMAGES = {}
#: The heart rate readout, by the 3: the rate, centered, in the gauges'
#: value font, with a red heart (the low battery's red) centered above it,
#: the two centered on the time vertically. In watch face units: how far
#: right of the 9 uv_layout's column starts, how far the readout's middle
#: is from the screen's right edge, the heart's gap above the rate, the
#: rate's digit height, and the UV index's.
HEART_RATE = dict(inset=11.0, edge=53.3, heart_gap=8.0, value=40.0, digits=40.0)
HEART_ICON = dict(width=26.0, color=TEMPERATURE_COLORS["hot"])
#: The UV index readout by the 9, laid out as the heart rate is (see
#: uv_index): the index, colored by the WHO scale, with DataDial's "UV"
#: icon, orange, centered above it. In watch face units: uv_layout's
#: offsets (how far its left edge is left of HEART_RATE's `inset`, and
#: how far right of that edge an index starts), the icon's gap above the
#: index (the heart's), and how far the readout's middle is from the
#: screen's left edge.
UV = dict(icon_out=5.0, value_in=15.0, icon_gap=8.0, edge=43.3)
#: The UV index's WHO levels, lowest first: (name, lowest index, color), in
#: the brighter shades DataDial uses on black: green, yellow, orange, red
#: and violet.
UV_LEVELS = (("low", 0, "#3DDC57"), ("moderate", 3, "#FFD60A"), ("high", 6, "#FF9500"),
             ("very_high", 8, "#FF3B30"), ("extreme", 11, "#AF52DE"))


def ellipse_path(cx, cy, rx, ry):
    """SVG path data for an ellipse, as four cubic Bezier curves."""
    k = 0.5523  # the control point distance for a quarter circle
    return (f"M{cx + rx} {cy}C{cx + rx} {cy + k * ry} {cx + k * rx} {cy + ry} {cx} {cy + ry}"
            f"C{cx - k * rx} {cy + ry} {cx - rx} {cy + k * ry} {cx - rx} {cy}"
            f"C{cx - rx} {cy - k * ry} {cx - k * rx} {cy - ry} {cx} {cy - ry}"
            f"C{cx + k * rx} {cy - ry} {cx + rx} {cy - k * ry} {cx + rx} {cy}Z")


#: The steps, calorie and elevation gauges' icons, below their values:
#: DataDial's footprints, flame and mountain (its art/steps.svg,
#: art/flame.svg and art/mountain.svg), orange. Each one's height in watch
#: face units and its SVG paths in a 24 x 24 box, with each path's fill
#: rule: the footprints are two soles and two heels; the flame is an outer
#: flame with a smaller one cut out of its core (even-odd); the mountain
#: is two peaks, its snowcap the same color.
SVG_ICONS = {
    "gauge_steps": dict(height=30.0, paths=tuple(
        (ellipse_path(*e), "nonzero")
        for e in ((7.5, 7.5, 3.2, 5), (7.5, 15.8, 2.5, 2.3), (16.5, 10.5, 3.2, 5),
                  (16.5, 18.8, 2.5, 2.3)))),
    "gauge_flame": dict(height=28.0, paths=(
        ("M12.5 2C13.3 6 11 8.2 9.5 10 9.2 8.6 8.6 7.6 7.6 7 7.8 9.2 4.5 11.5 4.5 15.2 "
         "4.5 19 7.9 22 12 22S19.5 19 19.5 15.2C19.5 9.5 15.5 5 12.5 2ZM12 19.5C10.3 19.5 "
         "9 18.3 9 16.7 9 14.8 10.6 13.9 11.6 12.2 12.3 14 15 14.7 15 16.8 15 18.3 13.7 "
         "19.5 12 19.5Z", "evenodd"),)),
    # DataDial's "UV" (its art/uv.svg).
    "gauge_uv": dict(height=23.0, paths=(
        ("M2 5H5V15C5 16.1 5.7 16.6 6.5 16.6 7.3 16.6 8 16.1 8 15V5H11V15C11 17.8 9 19.5 "
         "6.5 19.5 4 19.5 2 17.8 2 15Z", "nonzero"),
        ("M13 5H16.1L17.5 14.6 18.9 5H22L19.2 19.5H15.8Z", "nonzero"))),
    "gauge_mountain": dict(height=22.0, paths=(
        ("M1 21 9 6 13.5 14.4 16 10.5 23 21Z", "nonzero"),
        ("M9 6 11.2 10.1 10 11 9 9.8 7.9 11 6.8 10.1Z", "nonzero"))),
}
#: A big-number gauge (`big` in GAUGES): no pointer, hub, labels or unit,
#: only its tick marks around its value, large and centered in the ring,
#: with its icon at the bottom, in the ring's opening. In watch face units:
#:
#: - sizes: the value's digit height (in the gauges' value font) by how
#:   many digits it has, the largest that fits each: (numbers below this,
#:   height), the last for the rest. Up to three digits are as large as
#:   the space above the tallest icon allows; four and five fit inside the
#:   ticks with about 5 to spare.
#: - icon_bottom: how far below the center the icon's bottom edge is
#:   (inside the gauge's box).
#: - unit, unit_gap: for a gauge with a `unit_label`, the label's capital
#:   height and its gap above the value.
BIG_VALUE = dict(sizes=((1000, 40.0), (10000, 28.0), (None, 22.0)), icon_bottom=59.0,
                 unit=11.0, unit_gap=4.0)
#: The big values' characters and their image names.
BIG_CHARS = {**{str(n): str(n) for n in range(10)}, "-": "minus"}
#: The gauges' value characters and their image names.
GAUGE_CHARS = {**{str(n): str(n) for n in range(10)}, "-": "minus", "f": "f", "t": "t",
               "h": "h"}
#: The gauges' image sizes and the pointer's length (set by
#: render_gauges): "<name>_dial" and "hub" (pixels square), "digits" (each
#: digit's (width, height) in pixels) and "pointer" (watch face units).
GAUGE_IMAGES = {}


def gauge_font(height, weight=None):
    """GAUGE_FONT at the size that makes its capitals `height` pixels tall
    (at `weight` instead of its own, if given), and the top and bottom of
    its capitals and digits, with their curves' overshoot, from the
    baseline."""
    axes = dict(GAUGE_FONT["axes"], **({"Weight": weight} if weight else {}))

    def load(size):
        font = ImageFont.truetype(str(GAUGE_FONT["file"]), size)
        variable = font.get_variation_axes() if axes else []
        if variable:
            font.set_variation_by_axes([axes.get(a["name"].decode(), a["default"])
                                        for a in variable])
        return font
    probe = load(1000)
    top, bottom = probe.getbbox("H", anchor="ls")[1::2]
    font = load(round(1000 * height / (bottom - top)))
    box = font.getbbox("HOS0123456789", anchor="ls")
    return font, box[1], box[3]


def render_gauge_text(text, height, color=VALUE_COLOR, trailing=False, weight=None):
    """Text in GAUGE_FONT (at `weight`, if given), its capitals `height`
    pixels tall, as an image from the capitals' top to the baseline (and
    the curves' overshoot past them). Characters are spaced by their advance and GAUGE_FONT's
    tracking, which also follows the last one when `trailing`."""
    font, top, bottom = gauge_font(height, weight=weight)
    gap = GAUGE_FONT["tracking"] * height
    widths = [font.getlength(ch) for ch in text]
    width = sum(widths) + gap * (len(text) - (0 if trailing else 1))
    img = Image.new("RGBA", (math.ceil(width), bottom - top), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    x = 0.0
    for ch, w in zip(text, widths):
        draw.text((x, -top), ch, font=font, fill=rgb(color), anchor="ls")
        x += w + gap
    return img


def gauge_ring(gauge):
    """A gauge's tick ring: (inner radius, length, width), GAUGE's
    `ticks`."""
    return GAUGE["ticks"]


def gauge_center(gauge):
    """A gauge's center on the face: `distance` out along its angle, then
    `shift` toward the face's middle row (the top ones down, the bottom
    ones up)."""
    x, y = polar(gauge["angle"], GAUGE["distance"])
    return x, y + (GAUGE["shift"] if y < C else -GAUGE["shift"])


def gauge_arc(gauge):
    """A gauge's scale's span in degrees."""
    return gauge.get("arc", GAUGE["arc"])


def gauge_angle(gauge, value):
    """The angle, clockwise from 12, of a value on a gauge's scale."""
    lo, hi = gauge["scale"]
    return -gauge_arc(gauge) / 2 + (value - lo) * gauge_arc(gauge) / (hi - lo)


def render_gauge_dial(gauge):
    """A gauge's track (see GAUGE's `track`) and labels, and its redline if
    it has one: one image the size of the gauge, <name>_dial.png. Returns the master and
    its size in units."""
    inner, length, width = gauge_ring(gauge)
    red = GAUGE["redline"]
    # Room for the track (as wide as the bar) and the marker dot.
    reach = max(GAUGE["bar"]["width"] / 2, GAUGE["dot"]["radius"] + GAUGE["dot"]["edge"])
    size = math.ceil(2 * (inner + length / 2 + reach + 1))
    k = DRAW_SCALE
    img = Image.new("RGBA", (size * k,) * 2, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    c = size / 2
    if "redline" in gauge:
        # An arc band across the ticks' middle, from the first tick's outer
        # side to the last's, drawn first so the ticks lie over it.
        lo, hi = gauge["redline"]
        r0 = inner + length / 2 - red["width"] / 2
        r1 = r0 + red["width"]
        half = math.degrees(width / 2 / r0)
        a0, a1 = gauge_angle(gauge, lo) - half, gauge_angle(gauge, hi) + half
        steps = 48
        arc = [a0 + (a1 - a0) * i / steps for i in range(steps + 1)]
        band = ([(c + r1 * math.sin(math.radians(a)), c - r1 * math.cos(math.radians(a)))
                 for a in arc] +
                [(c + r0 * math.sin(math.radians(a)), c - r0 * math.cos(math.radians(a)))
                 for a in reversed(arc)])
        draw.polygon([(x * k, y * k) for x, y in band], fill=rgb(red["color"]))
    # The track: the scale's whole arc along the ring's middle, as wide as
    # the bar, its ends round.
    mid = inner + length / 2
    half = GAUGE["bar"]["width"] / 2
    a0, a1 = gauge_angle(gauge, gauge["scale"][0]), gauge_angle(gauge, gauge["scale"][1])
    draw.arc([(c - mid - half) * k, (c - mid - half) * k, (c + mid + half) * k,
              (c + mid + half) * k], a0 - 90, a1 - 90, fill=rgb(GAUGE["track"]),
             width=round(2 * half * k))
    for a in (a0, a1):
        x, y = c + mid * math.sin(math.radians(a)), c - mid * math.cos(math.radians(a))
        draw.ellipse([(x - half) * k, (y - half) * k, (x + half) * k, (y + half) * k],
                     fill=rgb(GAUGE["track"]))
    # The labels, each with its outer edge `gap` inside the ticks.
    limit = inner - GAUGE["labels"]["gap"]
    for value, text in gauge["labels"]:
        label = render_gauge_text(text, GAUGE["labels"]["height"] * k)
        w, h = label.width / k, label.height / k
        a = math.radians(gauge_angle(gauge, value))
        reach = abs(w / 2 * math.sin(a)) + abs(h / 2 * math.cos(a))
        distance = limit - reach
        x, y = c + distance * math.sin(a), c - distance * math.cos(a)
        img.alpha_composite(label, (round((x - w / 2) * k), round((y - h / 2) * k)))
    # The unit, small, right of the hub.
    if "unit" in gauge:
        label = render_gauge_text(gauge["unit"], GAUGE["unit"] * k)
        img.alpha_composite(label, (round((c + GAUGE["hub"][0][0] + GAUGE["labels"]["gap"]) * k),
                                    round(c * k - label.height / 2)))
    name = f"{gauge['name']}_dial"
    master = img.resize((size * MASTER_SCALE,) * 2, Image.LANCZOS)
    MASTERS.mkdir(parents=True, exist_ok=True)
    master.save(MASTERS / f"{name}.png")
    master.resize((size * SCALE,) * 2, Image.LANCZOS).save(DRAWABLE / f"{name}.png")
    GAUGE_IMAGES[name] = size * SCALE
    return master, size


def render_gauge_pointer():
    """The gauges' pointer: orange, widening from the hub to a point, to
    `gap` short of the ticks: gauge_pointer.png."""
    p = GAUGE["pointer"]
    GAUGE_IMAGES["pointer"] = GAUGE["ticks"][0] - p["gap"]
    c = HandCanvas("gauge_pointer", dict(length=GAUGE_IMAGES["pointer"] / R,
                                         outline=p["outline"]))
    c.draw.polygon(c.polygon(p["outline"]), fill=rgb(ORANGE))
    c.save()


def render_gauge_hub():
    """The gauges' hub, drawn large: gauge_hub.png. Returns the master."""
    size = 2 * math.ceil(GAUGE["hub"][0][0] + 1)
    k = DRAW_SCALE
    img = Image.new("RGBA", (size * k,) * 2, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    c = size * k / 2
    for radius, color in GAUGE["hub"]:
        r = radius * k
        draw.ellipse([c - r, c - r, c + r, c + r], fill=rgb(color))
    master = img.resize((size * MASTER_SCALE,) * 2, Image.LANCZOS)
    master.save(MASTERS / "gauge_hub.png")
    master.resize((size * SCALE,) * 2, Image.LANCZOS).save(DRAWABLE / "gauge_hub.png")
    GAUGE_IMAGES["hub"] = size * SCALE
    return master


def render_gauge_digits():
    """The values' characters (GAUGE_CHARS) in the gauges' font, each with
    its spacing after it: gauge_digit_<name>.png, and in the goal's green,
    gauge_digit_goal_<name>.png. Letters (a unit, "ft")
    are small, centered in an image as tall as a digit's. The watch's
    images are drawn straight at their pixel size, for crisp text (drawn
    large and scaled down, their edges came out soft), and the masters at
    theirs. Returns the masters by character."""
    weight = GAUGE["value"]["weight"]

    def glyph(ch, scale):
        """One character's image at `scale` pixels per unit."""
        height = GAUGE["value"]["height"] * scale
        img = render_gauge_text(ch, height, trailing=True, weight=weight)
        if ch.isalpha():
            small = render_gauge_text(ch, height * GAUGE["value"]["unit"], trailing=True,
                                      weight=weight)
            img = Image.new("RGBA", (small.width, img.height), (0, 0, 0, 0))
            img.alpha_composite(small, (0, (img.height - small.height) // 2))
        return img

    masters = {}
    GAUGE_IMAGES["digits"] = {}
    for ch, name in GAUGE_CHARS.items():
        master = glyph(ch, MASTER_SCALE)
        master.save(MASTERS / f"gauge_digit_{name}.png")
        img = glyph(ch, SCALE)
        img.save(DRAWABLE / f"gauge_digit_{name}.png")
        GAUGE_IMAGES["digits"][ch] = img.size
        masters[ch] = master
        # The same in the goal's green (see GOAL_COLOR).
        green = Image.new("RGBA", img.size, rgb(GOAL_COLOR))
        green.putalpha(img.getchannel("A"))
        green.save(DRAWABLE / f"gauge_digit_goal_{name}.png")
    # The big-number gauges' characters (BIG_VALUE), a set per size, white,
    # green and red: gauge_big<tier>_digit_<name>.png, ..._digit_goal_<name>.png
    # and ..._digit_low_<name>.png.
    GAUGE_IMAGES["big_digits"] = []
    for tier, (_, height) in enumerate(BIG_VALUE["sizes"]):
        sizes = {}
        for ch, name in BIG_CHARS.items():
            for prefix, color in ((f"gauge_big{tier}_digit", VALUE_COLOR),
                                  (f"gauge_big{tier}_digit_goal", GOAL_COLOR),
                                  (f"gauge_big{tier}_digit_low", BATTERY_LOW["color"])):
                master, size = render_value_glyph(ch, height, color, f"{prefix}_{name}")
                if color == VALUE_COLOR:
                    sizes[ch] = size
                    masters[f"big{tier}{ch}"] = master
        GAUGE_IMAGES["big_digits"].append(sizes)
    return masters


def render_day_names():
    """The day names (DAY_NAMES) and the date's digits in the gauges' value
    font, gray: day_<name>.png and date_digit_<n>.png."""
    for name in DAY_NAMES:
        _, DAY_IMAGES[name] = render_value_glyph(name, DAY_DATE["name"], VALUE_COLOR,
                                                 f"day_{name.lower()}", trailing=False)
    for d in "0123456789":
        _, DATE_GLYPHS[d] = render_value_glyph(d, DAY_DATE["date"], VALUE_COLOR,
                                               f"date_digit_{d}")


def render_heart_icon():
    """The heart rate's icon (HEART_ICON): a red heart, gauge_heart.png."""
    k = DRAW_SCALE
    # The classic heart curve, x = 16 sin^3 t and y = 13 cos t - 5 cos 2t -
    # 2 cos 3t - cos 4t, which spans 32 across and about 29 down.
    points = []
    for i in range(720):
        t = 2 * math.pi * i / 720
        points.append((16 * math.sin(t) ** 3,
                       -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t)
                         - math.cos(4 * t))))
    s = HEART_ICON["width"] / 32
    ys = [y for _, y in points]
    w = math.ceil(HEART_ICON["width"]) + 1
    h = math.ceil((max(ys) - min(ys)) * s) + 1
    img = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    ox, oy = w / 2, (h - (max(ys) - min(ys)) * s) / 2 - min(ys) * s
    ImageDraw.Draw(img).polygon([((ox + x * s) * k, (oy + y * s) * k) for x, y in points],
                                fill=rgb(HEART_ICON["color"]))
    master = img.resize((w * MASTER_SCALE, h * MASTER_SCALE), Image.LANCZOS)
    master.save(MASTERS / "gauge_heart.png")
    master.resize((w * SCALE, h * SCALE), Image.LANCZOS).save(DRAWABLE / "gauge_heart.png")
    GAUGE_IMAGES["gauge_heart"] = (w * SCALE, h * SCALE)


def svg_polygons(d, steps=24):
    """The closed polygons of SVG path data with absolute M, L, H, V, C, S
    and Z commands (a command's numbers may repeat it)."""
    import re
    tokens = re.findall(r"[MLHVCSZ]|-?\d*\.?\d+", d)
    polygons, poly = [], []
    pos = ctrl = (0.0, 0.0)
    i, cmd = 0, None

    def take(n):
        nonlocal i
        values = [float(t) for t in tokens[i:i + n]]
        i += n
        return [tuple(values[j:j + 2]) for j in range(0, n, 2)]

    def cubic(p0, c1, c2, p3):
        for k in range(1, steps + 1):
            t = k / steps
            u = 1 - t
            poly.append(tuple(u ** 3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t ** 3 * e
                              for a, b, c, e in zip(p0, c1, c2, p3)))

    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
        if cmd == "Z":
            polygons.append(poly)
            poly = []
            continue
        if cmd == "M":
            (pos,) = take(2)
            poly = [pos]
            cmd = "L"
        elif cmd == "L":
            (pos,) = take(2)
            poly.append(pos)
        elif cmd in "HV":
            v = float(tokens[i])
            i += 1
            pos = (v, pos[1]) if cmd == "H" else (pos[0], v)
            poly.append(pos)
        elif cmd == "C":
            c1, c2, end = take(6)
            cubic(pos, c1, c2, end)
            pos, ctrl = end, c2
        elif cmd == "S":
            c2, end = take(4)
            c1 = (2 * pos[0] - ctrl[0], 2 * pos[1] - ctrl[1])
            cubic(pos, c1, c2, end)
            pos, ctrl = end, c2
    return polygons


def render_svg_icon(name):
    """One of SVG_ICONS in orange, drawn large and scaled down to its
    height: <name>.png. Returns the master."""
    icon = SVG_ICONS[name]
    k = DRAW_SCALE
    paths = [(svg_polygons(d), rule) for d, rule in icon["paths"]]
    xs = [x for polys, _ in paths for poly in polys for x, _ in poly]
    ys = [y for polys, _ in paths for poly in polys for _, y in poly]
    s = icon["height"] / (max(ys) - min(ys))
    w = math.ceil((max(xs) - min(xs)) * s) + 2
    h = math.ceil(icon["height"]) + 2
    ox = w / 2 - (max(xs) + min(xs)) / 2 * s
    oy = 1 - min(ys) * s
    mask = Image.new("L", (w * k, h * k), 0)
    for polys, rule in paths:
        shape = Image.new("L", mask.size, 0)
        for poly in polys:
            layer = Image.new("L", mask.size, 0)
            ImageDraw.Draw(layer).polygon([((ox + x * s) * k, (oy + y * s) * k) for x, y in poly],
                                          fill=255)
            # Even-odd: each subpath flips what it covers (the layers are 0
            # or 255, so the difference is their XOR); nonzero: a union.
            shape = (ImageChops.difference(shape, layer) if rule == "evenodd"
                     else ImageChops.lighter(shape, layer))
        mask = ImageChops.lighter(mask, shape)
    img = Image.new("RGBA", mask.size, rgb(ORANGE))
    img.putalpha(mask)
    master = img.resize((w * MASTER_SCALE, h * MASTER_SCALE), Image.LANCZOS)
    master.save(MASTERS / f"{name}.png")
    master.resize((w * SCALE, h * SCALE), Image.LANCZOS).save(DRAWABLE / f"{name}.png")
    GAUGE_IMAGES[name] = (w * SCALE, h * SCALE)
    return master


def gauge_icon_top(cy):
    """The top of a gauge's icon, below its value, for the gauge center's
    y `cy`, in watch face units."""
    return (cy + GAUGE["hub"][0][0] + GAUGE["value"]["gap"] + GAUGE_IMAGES["digits"]["0"][1]
            + GAUGE_ICON_GAP)


def render_gauges():
    """Each gauge's dial, the shared pointer, hub and digits, the icons,
    and a review sheet per gauge at its review pointer and value
    (build/masters/<name>_gauge.png)."""
    render_gauge_pointer()
    hub = render_gauge_hub()
    digits = render_gauge_digits()
    icons = {n: render_svg_icon(n) for n in SVG_ICONS}
    icons["battery"] = Image.open(MASTERS / "battery_4.png")
    for gauge in GAUGES:
        if "unit_label" in gauge:
            _, GAUGE_IMAGES[f"unit_{gauge['name']}"] = render_value_glyph(
                gauge["unit_label"], BIG_VALUE["unit"], VALUE_COLOR, f"unit_{gauge['name']}",
                trailing=False)
    render_heart_icon()
    render_day_names()
    for ch, name in DATE_LINE_CHARS.items():
        _, DATE_LINE_GLYPHS[ch] = render_value_glyph(ch, DATE_LINE["height"], VALUE_COLOR,
                                                     f"date_line_{name}")
    pointer = Image.open(MASTERS / "gauge_pointer.png")
    w, top, _ = HAND_IMAGES["gauge_pointer"]
    k = MASTER_SCALE
    for gauge in GAUGES:
        dial, size = render_gauge_dial(gauge)
        # The review sheet, from the masters, on black.
        pad = 8 * k
        sheet = Image.new("RGBA", (dial.width + 2 * pad,) * 2, (0, 0, 0, 255))
        sheet.alpha_composite(dial, (pad, pad))
        cx = cy = pad + size / 2 * k
        big = gauge.get("big")
        tier = big_tier(gauge["review"]["pointer"]) if big else 0
        value_top, _, _, _, height, icon_top = gauge_value_layout(gauge, cy / k, tier)
        if "icon" in gauge:
            icon = icons[gauge["icon"]]
            sheet.alpha_composite(icon, (round(cx - icon.width / 2), round(icon_top * k)))
        # The value, then the pointer over it and the hub, as on the watch.
        shown = [digits[f"big{tier}{d}" if big else d] for d in gauge["review"]["value"]]
        trailing = GAUGE_FONT["tracking"] * height * k
        x = round(cx - (sum(d.width for d in shown) - trailing) / 2)
        y = round(value_top * k)
        for d in shown:
            sheet.alpha_composite(d, (x, y))
            x += d.width
        if big:
            sheet.convert("RGB").save(MASTERS / f"{gauge['name']}_gauge.png")
            continue
        layer = Image.new("RGBA", sheet.size, (0, 0, 0, 0))
        layer.alpha_composite(pointer, (round(cx - w * k / 2), round(cy - top * k)))
        angle = gauge_angle(gauge, gauge["review"]["pointer"])
        sheet.alpha_composite(layer.rotate(-angle, resample=Image.BICUBIC, center=(cx, cy)))
        sheet.alpha_composite(hub, (round(cx - hub.width / 2), round(cy - hub.height / 2)))
        sheet.convert("RGB").save(MASTERS / f"{gauge['name']}_gauge.png")


def render_images():
    DRAWABLE.mkdir(parents=True, exist_ok=True)
    measure_numerals()
    render_weather_icons()
    render_temperature_glyphs()
    render_heart_rate_glyphs()
    render_battery()
    render_gauges()
    render_clock_glyphs()


def render_clock_glyphs():
    """The time's characters (see CLOCK), white: time_<name>.png; the
    seconds' digits, smaller and in their color: seconds_<name>.png; and
    the battery hours' characters (see BATTERY_HOURS), white:
    battery_hours_<name>.png, and red below the low limit:
    battery_hours_low_<name>.png, cut to their ink so they center exactly
    under the battery (see render_value_glyph). All in the values' font."""
    for prefix, chars, glyphs, height, color, tight in (
            ("time", TIME_CHARS, TIME_GLYPHS, CLOCK["height"], VALUE_COLOR, False),
            ("seconds", SECONDS_CHARS, SECONDS_GLYPHS, CLOCK["seconds"],
             CLOCK["seconds_color"], False),
            ("battery_hours", BATTERY_HOURS_CHARS, BATTERY_HOURS_GLYPHS,
             BATTERY_HOURS["height"], VALUE_COLOR, True),
            ("battery_hours_low", BATTERY_HOURS_CHARS, {}, BATTERY_HOURS["height"],
             BATTERY_LOW["color"], True)):
        for ch, name in chars.items():
            _, glyphs[ch] = render_value_glyph(ch, height, color, f"{prefix}_{name}",
                                               tight=tight)


#: The test build's time (hour, minute, second), also the picker preview's.
#: The test build shows it, frozen, in place of the watch's time.
TEST_TIME = (8, 10, 18)
#: The test build's weather, in place of the watch's (the emulator often
#: has none): the WEATHER data sources' values, unit 2 being Fahrenheit.
TEST_WEATHER = {**dict(IS_AVAILABLE=1, IS_DAY=1, CONDITION=1, TEMPERATURE=72,
                        TEMPERATURE_UNIT=2, UV_INDEX=7),
                "DAYS.0.TEMPERATURE_LOW": 58, "DAYS.0.TEMPERATURE_HIGH": 79}
#: The test build's date, heart rate and battery, in place of the watch's:
#: Friday 20 March ([DAY_OF_WEEK] is 1 for Sunday), a heart rate of 72 and
#: 80% battery. (The complication gauges' samples are in GAUGES.)
TEST_SOURCES = {"[DAY_OF_WEEK]": 6, "[DAY]": 20, "[MONTH]": 3, "[HEART_RATE]": 72,
                "[BATTERY_PERCENT]": 80}


def write_xml(test=False):
    face = watch_face(test)
    ET.indent(face, space="    ")
    out = RES / "raw" / "watchface.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    body = ET.tostring(face, encoding="unicode")
    note = "Generated by tools/generate.py. Edit that script, not this file."
    if test:
        # No double hyphens: they aren't allowed in an XML comment.
        note = "TEST BUILD with a frozen time (generate.py test option). Don't ship this."
    header = f"<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<!-- {note} -->\n"
    out.write_text(header + body + "\n", encoding="utf-8", newline="\n")


def main():
    test = "--test" in sys.argv[1:]
    render_images()  # first: the XML needs the hand image sizes
    write_xml(test)
    print(f"Wrote {RES / 'raw' / 'watchface.xml'}{' (test build)' if test else ''}"
          f" and the images in {DRAWABLE}")


if __name__ == "__main__":
    main()
