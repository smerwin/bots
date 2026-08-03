"""Tests for a game canvas that does not fill its window.

Mirroring this Mac to an Apple TV left the EVE window 1710x1068 points
(3420x2136 device pixels) while `UIRoot` went on reporting a 3420x2079 canvas.
The host divided one by the other and got `scale_y = 1.947` where the truth is a
clean 2.0 with the canvas inset 57 pixels down the window.

**The failure is this repo's signature one.** The error is proportional to y, so
it is nothing at the top of the window and about 28 points at the bottom -- far
enough to land a click on the Neocom icon *next to* the intended one, and not
far enough to look like anything. Run 22 opened Inventory, Wallet, Directional
Scanner and Opportunities by itself over three hours. One of those stray clicks
switched the location info panel off, and then the bot's own repair branch --
which aims at exactly the right icon -- clicked 116 times without ever hitting
it, because it missed by the same offset. Every one of those clicks was reported
as dispatched. A click that lands on nothing reads exactly like a click that
lands.

Two numbers here are measured against the live client rather than reasoned out,
and the tests pin both:

* the inset is **57 pixels** and it is at the **top** -- an info-panel icon the
  UI tree placed at canvas y=75 rendered at y=134 in a capture of that window;
* the x axis is exact (3420 = 1710 x 2), which is what tells a genuinely uniform
  scale apart from two ratios that merely came out close.

The second matters because a non-square scale is a real configuration here, not
a hypothetical: the game has its own UI-scale setting independent of the OS
backing factor, and ratios of 1.684 / 1.743 are recorded in the host's own
comments. That case must keep the old per-axis behaviour, and does.

Nothing here reads a live game client, a bot, or a screenshot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))

import botlab_host  # noqa: E402

calibrate = botlab_host.calibrate_window_canvas

# The live geometry, read off the client while run 22 was stuck in it.
MIRRORED_CANVAS = (3420, 2079)
MIRRORED_POINTS = (1710, 1068)
MIRRORED_ORIGIN_Y = 39          # the window's own top, in screen points
MIRRORED_BACKING = 2.0
MEASURED_INSET_Y = 57

# The same client before mirroring: the canvas fills the window exactly.
FILLED_CANVAS = (3420, 2136)


def screen_point_for_canvas_position(canvas_x, canvas_y, canvas, points,
                                     origin_x, origin_y, backing):
    """Run a canvas position through the host's whole coordinate path.

    This is the *composition* the bot and host actually perform: the host
    reports a rect in game pixels, `BotFramework.elm` adds the UI position to
    it unscaled, and `_windows_input` divides by the scale on the way out to
    `cg_input`. The rect half is the real `window_canvas_geometry` rather than
    a restatement of it -- mutation testing showed a restatement passes happily
    while the host itself drops the inset entirely.
    """
    rect = {
        "left": origin_x, "top": origin_y,
        "right": origin_x + points[0], "bottom": origin_y + points[1],
        "backing_scale": backing,
    }
    scaled_rect, scale_x, scale_y, _ = botlab_host.window_canvas_geometry(rect, canvas)
    return ((canvas_x + scaled_rect["left"]) / scale_x,
            (canvas_y + scaled_rect["top"]) / scale_y)


class InputConversionTests(unittest.TestCase):
    """The other half of the composition, pinned by reading the source.

    `_windows_input` divides an outbound coordinate by the same scales this
    calibration produces. That is one line and cannot be driven without a live
    `cg_input`, so it is read instead -- if it stops dividing, or starts
    dividing by something else, the arithmetic above no longer describes what
    reaches the client.
    """

    def test_outbound_coordinates_are_divided_by_the_calibrated_scales(self):
        with open(botlab_host.__file__) as handle:
            source = handle.read()
        self.assertIn("x / scale_x, y / scale_y", source)
        self.assertIn("scale_x = self._scale_x", source)
        self.assertIn("scale_y = self._scale_y", source)


class CalibrationTests(unittest.TestCase):
    def test_mirrored_window_is_a_uniform_scale_with_a_top_inset(self):
        scale_x, scale_y, inset_x, inset_y, w, h = calibrate(
            MIRRORED_CANVAS, MIRRORED_POINTS[0], MIRRORED_POINTS[1], MIRRORED_BACKING)
        self.assertEqual((scale_x, scale_y), (2.0, 2.0))
        self.assertEqual((inset_x, inset_y), (0, MEASURED_INSET_Y))
        self.assertEqual((w, h), MIRRORED_CANVAS)

    def test_the_fudged_per_axis_scale_is_what_the_inset_replaces(self):
        """The old code's answer, kept here so the difference is explicit."""
        fudged = MIRRORED_CANVAS[1] / MIRRORED_POINTS[1]
        self.assertAlmostEqual(fudged, 1.9466, places=4)
        _, scale_y, _, inset_y, _, _ = calibrate(
            MIRRORED_CANVAS, MIRRORED_POINTS[0], MIRRORED_POINTS[1], MIRRORED_BACKING)
        self.assertNotAlmostEqual(scale_y, fudged, places=4)
        self.assertGreater(inset_y, 0)

    def test_a_canvas_that_fills_its_window_is_unchanged(self):
        """The ordinary case must come out exactly as it always did."""
        scale_x, scale_y, inset_x, inset_y, w, h = calibrate(
            FILLED_CANVAS, MIRRORED_POINTS[0], MIRRORED_POINTS[1], MIRRORED_BACKING)
        self.assertEqual((inset_x, inset_y), (0, 0))
        self.assertEqual(scale_x, FILLED_CANVAS[0] / MIRRORED_POINTS[0])
        self.assertEqual(scale_y, FILLED_CANVAS[1] / MIRRORED_POINTS[1])
        self.assertEqual((w, h), FILLED_CANVAS)

    def test_a_genuinely_non_square_game_ui_scale_keeps_the_per_axis_divide(self):
        """1.684 / 1.743 is recorded in the host's own comments as real.

        It is not an inset and must not be treated as one -- doing so would
        put the whole difference between the axes into a bogus offset.
        """
        canvas = (2880, 1861)
        scale_x, scale_y, inset_x, inset_y, _, _ = calibrate(
            canvas, MIRRORED_POINTS[0], MIRRORED_POINTS[1], MIRRORED_BACKING)
        self.assertEqual((inset_x, inset_y), (0, 0))
        self.assertAlmostEqual(scale_x, 1.684, places=3)
        self.assertAlmostEqual(scale_y, 1.743, places=3)
        self.assertNotAlmostEqual(scale_x, scale_y, places=3)

    def test_an_unexplained_shortfall_falls_back_rather_than_guessing(self):
        """One exact axis is required, so a near-miss is not read as an inset."""
        canvas = (3419, 2079)  # x is one pixel off being exact
        scale_x, scale_y, inset_x, inset_y, _, _ = calibrate(
            canvas, MIRRORED_POINTS[0], MIRRORED_POINTS[1], MIRRORED_BACKING)
        self.assertEqual((inset_x, inset_y), (0, 0))
        self.assertNotEqual(scale_x, scale_y)

    def test_a_shortfall_past_the_bound_falls_back(self):
        canvas = (3420, 2136 - botlab_host.CANVAS_INSET_MAX_PIXELS - 1)
        _, _, inset_x, inset_y, _, _ = calibrate(
            canvas, MIRRORED_POINTS[0], MIRRORED_POINTS[1], MIRRORED_BACKING)
        self.assertEqual((inset_x, inset_y), (0, 0))

    def test_a_canvas_larger_than_its_window_is_not_a_negative_inset(self):
        canvas = (3420, 2200)
        _, _, inset_x, inset_y, _, _ = calibrate(
            canvas, MIRRORED_POINTS[0], MIRRORED_POINTS[1], MIRRORED_BACKING)
        self.assertGreaterEqual(inset_x, 0)
        self.assertGreaterEqual(inset_y, 0)

    def test_a_shortfall_rounding_below_zero_does_not_become_a_negative_inset(self):
        """The tolerance admits a shortfall just under zero; the clamp catches it.

        The bound is `-1 < short` so that a value which should be exactly zero
        is not rejected for floating-point dust. That admits shortfalls in
        (-1, 0), and `round` takes -0.53 to -1 -- an inset that would shift
        every coordinate the wrong way by half a point. Reachable only with a
        non-integer backing scale, which is why it needs its own case: with a
        clean 2.0 every shortfall is a whole number.
        """
        _, _, inset_x, inset_y, _, _ = calibrate((3419, 2136), 1710, 1068, 1.9995)
        self.assertEqual((inset_x, inset_y), (0, 0))

    def test_no_canvas_size_yet_falls_back_to_the_backing_scale(self):
        """The first call, before any ReadFromWindow has answered."""
        scale_x, scale_y, inset_x, inset_y, _, _ = calibrate(
            None, MIRRORED_POINTS[0], MIRRORED_POINTS[1], MIRRORED_BACKING)
        self.assertEqual((scale_x, scale_y), (2.0, 2.0))
        self.assertEqual((inset_x, inset_y), (0, 0))


class ClickTargetTests(unittest.TestCase):
    """The composed path, against the one position measured on the live client.

    The location info panel's own toggle -- the icon whose 116 missed clicks
    are what made this findable.
    """

    ICON_CANVAS_X, ICON_CANVAS_Y = 216, 87   # centre, from the UI tree
    ICON_RENDERED_IMAGE_Y = 134              # top edge, from a window capture

    def test_the_toggle_click_lands_on_the_toggle(self):
        x, y = screen_point_for_canvas_position(
            self.ICON_CANVAS_X, self.ICON_CANVAS_Y,
            MIRRORED_CANVAS, MIRRORED_POINTS, 0, MIRRORED_ORIGIN_Y, MIRRORED_BACKING)
        # Where the icon really is: its rendered position in the window image,
        # converted to screen points. The icon is 24 game pixels tall.
        expected_y = MIRRORED_ORIGIN_Y + (self.ICON_RENDERED_IMAGE_Y + 12) / MIRRORED_BACKING
        self.assertAlmostEqual(x, 108.0, places=1)
        self.assertAlmostEqual(y, expected_y, delta=1.0)

    def test_the_old_arithmetic_missed_it_by_the_inset(self):
        """Guard against a fix that moves the click without landing it."""
        fudged_scale = MIRRORED_CANVAS[1] / MIRRORED_POINTS[1]
        old_y = (self.ICON_CANVAS_Y + int(MIRRORED_ORIGIN_Y * fudged_scale)) / fudged_scale
        _, new_y = screen_point_for_canvas_position(
            self.ICON_CANVAS_X, self.ICON_CANVAS_Y,
            MIRRORED_CANVAS, MIRRORED_POINTS, 0, MIRRORED_ORIGIN_Y, MIRRORED_BACKING)
        self.assertAlmostEqual(old_y, 83.7, delta=0.6)
        # Half the inset, because the correction is applied in game pixels and
        # read back in points.
        self.assertAlmostEqual(new_y - old_y, MEASURED_INSET_Y / 2.0, delta=1.0)

    def test_a_filled_canvas_round_trips_unchanged(self):
        """The regression that matters: no inset must mean no movement."""
        for canvas_y in (0, 500, 2000):
            x, y = screen_point_for_canvas_position(
                100, canvas_y, FILLED_CANVAS, MIRRORED_POINTS,
                0, MIRRORED_ORIGIN_Y, MIRRORED_BACKING)
            self.assertAlmostEqual(x, 50.0, places=6)
            self.assertAlmostEqual(y, MIRRORED_ORIGIN_Y + canvas_y / 2.0, places=6)

    def test_the_canvas_origin_is_where_the_canvas_starts(self):
        """A UI position of (0, 0) is the canvas corner, not the window's."""
        x, y = screen_point_for_canvas_position(
            0, 0, MIRRORED_CANVAS, MIRRORED_POINTS, 0, MIRRORED_ORIGIN_Y, MIRRORED_BACKING)
        self.assertAlmostEqual(x, 0.0, places=6)
        self.assertAlmostEqual(y, MIRRORED_ORIGIN_Y + MEASURED_INSET_Y / 2.0, places=6)


if __name__ == "__main__":
    unittest.main()
