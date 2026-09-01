from manim import *

class ChapterOneTermux(Scene):
    def construct(self):

        # Title
        title = Text(
            "Termux Mastery\nChapter 1: What is Termux?",
            font_size=48
        )

        self.play(Write(title))
        self.wait(2)
        self.play(FadeOut(title))


        # Android ecosystem
        android = Text("Android Phone", font_size=42)
        linux = Text("Linux Environment", font_size=42)
        termux = Text("Termux", font_size=50, color=BLUE)

        arrow1 = Arrow(
            android.get_bottom(),
            linux.get_top()
        )

        arrow2 = Arrow(
            linux.get_bottom(),
            termux.get_top()
        )

        group = VGroup(android, linux, termux).arrange(DOWN, buff=1)

        self.play(Write(android))
        self.play(Create(arrow1), Write(linux))
        self.play(Create(arrow2), Write(termux))

        self.wait(2)


        # Explanation
        self.play(FadeOut(group))

        text = Text(
            "Termux is an Android application\n"
            "that provides a Linux terminal\n"
            "without requiring root access.",
            font_size=38
        )

        self.play(Write(text))
        self.wait(3)

        self.play(FadeOut(text))


        # Terminal animation

        terminal_box = RoundedRectangle(
            width=8,
            height=3,
            corner_radius=0.2,
            color=GREEN
        )

        terminal_text = Text(
            "$ pkg update\n"
            "$ pkg install python\n"
            "$ python script.py",
            font_size=35,
            color=GREEN
        )

        self.play(Create(terminal_box))
        self.play(Write(terminal_text))

        self.wait(3)


        # Capabilities

        self.play(
            FadeOut(terminal_box),
            FadeOut(terminal_text)
        )

        capabilities = BulletedList(
            "Run Linux commands",
            "Write Python, Rust, C programs",
            "Use Git and development tools",
            "Learn cybersecurity",
            "Automate tasks"
        )

        self.play(Write(capabilities))
        self.wait(4)

        self.play(FadeOut(capabilities))


        # Ending

        end = Text(
            "Chapter 1 Complete\n"
            "Next: Installing & Setting Up Termux",
            font_size=42
        )

        self.play(Write(end))
        self.wait(3)
