import curses
import json
import appdirs
import os
import ueberzug.lib.v0 as ueberzug
from .rust_module.nuber import Book, Image


class Reader:
    def __init__(self, path: str) -> None:
        self.path = path
        self.stdscr: curses.window = curses.initscr()
        self.rows, self.cols = self.stdscr.getmaxyx()
        self.cahce_dir = os.path.join(appdirs.user_cache_dir(), "nuber")
        if not os.path.exists(self.cahce_dir):
            os.mkdir(self.cahce_dir)
        self.state_file = os.path.join(appdirs.user_cache_dir(), "nuber", "state.json")
        curses.noecho()
        curses.curs_set(0)
        self.book = Book(path)

        self.offset = 0
        self.current_position = 0
        self.chapter_idx = 0
        self.positions = [0] * self.book.get_num_chapters()
        self.placements = {}
        self.current_chapter_placements = []
        self.word_count_per_line = []

        if os.path.exists(self.state_file):
            with open(self.state_file, "r") as state_file:
                states = json.loads(state_file.read())
                try:
                    state = states[self.path]
                    self.positions = state["positions"]
                    self.chapter_idx = state["chapter_idx"]
                    self.current_position = self.positions[self.chapter_idx]
                    self.book.set_current_chapter(self.chapter_idx)
                except KeyError:
                    pass

    def add_image(self, canvas: ueberzug.Canvas, position: tuple[int, int], info: Image) -> None:
        img_id = f"{position[0]}{position[1]}{info.path}"
        if img_id in self.placements:
            placement = self.placements[img_id]
        else:
            placement = canvas.create_placement(img_id)
            placement.path = info.path
            self.placements[img_id] = placement
        placement.x, placement.y = position
        placement.width, placement.height = info.size
        self.current_chapter_placements.append((position[1], placement))

    def render_chapter(self, canvas: ueberzug.Canvas) -> None:
        chapter = self.book.render_current_chapter()
        self.chapter_rows = max(self.rows, len(chapter))
        self.pad: curses.window = curses.newpad(self.chapter_rows, self.cols)
        self.word_count_per_line = []
        for line_num, elements in enumerate(chapter):
            current_pos = 0
            word_count = 0
            for element in elements:
                if info := element.image_info:
                    if element.text.startswith("S"):
                        self.add_image(canvas, (current_pos, line_num), info)
                    current_pos += len(element.text)
                    continue
                current_pos += self.addstr(line_num, current_pos, element.text, element.style)
                word_count += len(element.text.split())
            self.word_count_per_line.append(word_count)

    def determine_visibility(self, y: int, h: int) -> ueberzug.Visibility:
        y_pos = y - self.offset
        padding = 1
        if y_pos + h + padding < 0:
            return ueberzug.Visibility.INVISIBLE
        if y_pos - padding > self.rows:
            return ueberzug.Visibility.INVISIBLE
        return ueberzug.Visibility.VISIBLE

    def addstr(self, y: int, x: int, text: str, styles: list) -> int:
        formatting = curses.A_NORMAL
        for style in styles:
            if style == "bold":
                formatting = formatting | curses.A_BOLD
            elif style == "italic":
                formatting = formatting | curses.A_ITALIC
            elif style == "reverse":
                formatting = formatting | curses.A_REVERSE
            elif style == "underline":
                formatting = formatting | curses.A_UNDERLINE

        try:
            self.pad.addstr(y, x, text, formatting)
            return len(text)
        except curses.error:
            return 0

    def update_offset(self) -> None:
        self.offset = 0
        while self.current_position > sum(self.word_count_per_line[:self.offset]):
            self.offset += 1

    @staticmethod
    def action_noop(_: ueberzug.Canvas) -> None:
        pass

    def action_scroll_down(self, canvas: ueberzug.Canvas) -> None:
        if self.offset < self.chapter_rows - self.rows:
            self.current_position += self.word_count_per_line[self.offset]
            self.offset += 1
            self.redraw(canvas)

    def action_scroll_up(self, canvas: ueberzug.Canvas) -> None:
        if self.offset > 0:
            self.current_position -= self.word_count_per_line[self.offset]
            self.offset -= 1
            self.redraw(canvas)

    def action_next_chapter(self, canvas: ueberzug.Canvas) -> None:
        if self.book.next_chapter():
            self.positions[self.chapter_idx] = self.current_position
            self.chapter_idx += 1
            self.clear(canvas)
            self.current_position = self.positions[self.chapter_idx]
            self.render_chapter(canvas)
            self.update_offset()
            self.redraw(canvas)

    def action_previous_chapter(self, canvas: ueberzug.Canvas) -> None:
        if self.book.previous_chapter():
            self.positions[self.chapter_idx] = self.current_position
            self.chapter_idx -= 1
            self.clear(canvas)
            self.current_position = self.positions[self.chapter_idx]
            self.render_chapter(canvas)
            self.update_offset()
            self.redraw(canvas)

    def action_quit(self, _: ueberzug.Canvas) -> None:
        self.positions[self.chapter_idx] = self.current_position
        states = {}
        if os.path.exists(self.state_file):
            with open(self.state_file, "r") as state_file:
                states = json.loads(state_file.read())

        states[self.path] = {
                "positions": self.positions,
                "chapter_idx": self.chapter_idx,
                }

        with open(self.state_file, "w") as state_file:
            state_file.write(json.dumps(states))
        curses.endwin()
        exit(0)

    def action_resize(self, canvas: ueberzug.Canvas) -> None:
        self.clear(canvas)
        self.book.update_term_info()
        self.rows, self.cols = self.stdscr.getmaxyx()
        self.render_chapter(canvas)
        self.update_offset()
        self.redraw(canvas)


    def on_key(self, key: int, canvas: ueberzug.Canvas) -> None:
        keys = {
                ord("h"): self.action_previous_chapter,
                ord("j"): self.action_scroll_down,
                ord("k"): self.action_scroll_up,
                ord("l"): self.action_next_chapter,
                ord("q"): self.action_quit,
                curses.KEY_RESIZE: self.action_resize,
                }

        action = keys.get(key, self.action_noop)
        action(canvas)

    def clear(self, canvas: ueberzug.Canvas) -> None:
        try:
            self.pad.clear()
            with canvas.synchronous_lazy_drawing:
                for _, placement in self.current_chapter_placements:
                    placement.visibility = ueberzug.Visibility.INVISIBLE
            self.current_chapter_placements = []
        except AttributeError:
            pass

    def redraw(self, canvas: ueberzug.Canvas) -> None:
        if self.offset > (offset := self.chapter_rows - self.rows):
            self.offset = offset
        self.pad.refresh(self.offset, 0, 0, 0, self.rows - 1, self.cols - 1)
        with canvas.synchronous_lazy_drawing:
            for initial_y, placement in self.current_chapter_placements:
                visibility = self.determine_visibility(initial_y, placement.height)
                if visibility == ueberzug.Visibility.VISIBLE:
                    placement.y = initial_y - self.offset
                placement.visibility = visibility

    @ueberzug.Canvas()
    def loop(self, canvas: ueberzug.Canvas) -> None:
        self.render_chapter(canvas)
        self.update_offset()
        self.redraw(canvas)
        while True:
            ch = self.pad.getch()
            self.on_key(ch, canvas)
