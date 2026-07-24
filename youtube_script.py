"""
Textual Input Demo Application
A simple app demonstrating various input methods in Textual
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Button, Input, TextArea, Label, Select, Static
from textual.reactive import reactive
from textual.message import Message


class InputDemoApp(App):
    """A Textual app demonstrating user input methods."""

    CSS = """
    #main-container {
        height: 100%;
        padding: 1;
        background: $surface;
    }

    #input-section {
        height: 70%;
        border: solid $primary;
        padding: 1;
        margin: 1;
    }

    #output-section {
        height: 30%;
        border: solid $secondary;
        padding: 1;
        margin: 1;
        background: $panel;
    }

    #output-text {
        height: 100%;
        background: $surface;
        padding: 1;
    }

    .input-row {
        height: 3;
        margin-bottom: 1;
    }

    .input-row Label {
        width: 20%;
        content-align: right middle;
        padding-right: 1;
    }

    .input-row Input {
        width: 80%;
    }

    #textarea-container {
        height: 10;
        margin-bottom: 1;
    }

    #textarea-container Label {
        width: 100%;
        padding-bottom: 0;
    }

    #textarea-container TextArea {
        height: 100%;
        width: 100%;
    }

    #button-row {
        height: 3;
        align: center middle;
    }

    Button {
        margin: 0 1;
    }

    #select-row {
        height: 3;
        margin-bottom: 1;
    }

    #select-row Label {
        width: 20%;
        content-align: right middle;
        padding-right: 1;
    }

    #select-row Select {
        width: 80%;
    }
    """

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Container(
            Container(
                Vertical(
                    # Name input
                    Horizontal(
                        Label("Name:"),
                        Input(placeholder="Enter your name", id="name-input"),
                        classes="input-row",
                    ),
                    # Email input
                    Horizontal(
                        Label("Email:"),
                        Input(placeholder="Enter your email", id="email-input"),
                        classes="input-row",
                    ),
                    # Select dropdown
                    Horizontal(
                        Label("Role:"),
                        Select(
                            [
                                ("Select a role...", ""),
                                ("Developer", "dev"),
                                ("Designer", "design"),
                                ("Manager", "manager"),
                                ("QA Engineer", "qa"),
                            ],
                            id="role-select",
                            value="",
                        ),
                        classes="input-row",
                        id="select-row",
                    ),
                    # Text area
                    Container(
                        Label("Message:"),
                        TextArea(
                            placeholder="Enter your message here...",
                            id="message-textarea",
                        ),
                        id="textarea-container",
                    ),
                    # Buttons
                    Horizontal(
                        Button("Submit", variant="primary", id="submit-btn"),
                        Button("Clear", variant="error", id="clear-btn"),
                        Button("Exit", variant="default", id="exit-btn"),
                        id="button-row",
                    ),
                    id="input-section",
                ),
                # Output section
                Container(
                    Label("Output:", id="output-label"),
                    Static("Waiting for input...", id="output-text"),
                    id="output-section",
                ),
                id="main-container",
            ),
        )
        yield Footer()

    def on_mount(self) -> None:
        """Set up the app when it starts."""
        self.title = "Textual Input Demo"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        button_id = event.button.id

        if button_id == "submit-btn":
            self.handle_submit()
        elif button_id == "clear-btn":
            self.clear_all()
        elif button_id == "exit-btn":
            self.exit()

    def handle_submit(self) -> None:
        """Process and display the submitted input."""
        # Get all input values
        name = self.query_one("#name-input", Input).value
        email = self.query_one("#email-input", Input).value
        role_select = self.query_one("#role-select", Select)
        role = role_select.value
        message = self.query_one("#message-textarea", TextArea).text

        # Get role label
        role_label = ""
        for option in role_select.options:
            if option[1] == role:
                role_label = option[0]
                break

        # Build output
        if not name and not email and not role and not message:
            output = "⚠️ No input provided. Please fill in some fields."
        else:
            output = "✅ Input Received:\n\n"
            output += f"📝 Name: {name if name else '(not provided)'}\n"
            output += f"✉️ Email: {email if email else '(not provided)'}\n"
            output += f"💼 Role: {role_label if role else '(not selected)'}\n"
            output += f"💬 Message: {message if message else '(not provided)'}"

        # Update output
        self.query_one("#output-text", Static).update(output)

    def clear_all(self) -> None:
        """Clear all input fields."""
        self.query_one("#name-input", Input).value = ""
        self.query_one("#email-input", Input).value = ""
        self.query_one("#role-select", Select).value = ""
        self.query_one("#message-textarea", TextArea).text = ""
        self.query_one("#output-text", Static).update("Waiting for input...")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key press in input fields."""
        self.handle_submit()


if __name__ == "__main__":
    app = InputDemoApp()
    app.run()
