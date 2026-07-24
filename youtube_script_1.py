"""
Topic Manager - A Textual App for Topic Input and Organization
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Button, Input, Label, Static, ListView, ListItem
from textual.reactive import reactive
from datetime import datetime
import json
import os


class TopicManager(App):
    """A Textual app for managing topics with categories and priorities."""

    CSS = """
    #main-container {
        height: 100%;
        padding: 1;
        background: $surface;
    }

    #left-panel {
        width: 40%;
        height: 100%;
        border: solid $primary;
        padding: 1;
        margin-right: 1;
    }

    #right-panel {
        width: 60%;
        height: 100%;
        border: solid $secondary;
        padding: 1;
    }

    #topic-list {
        height: 70%;
        border: solid $panel;
        margin-top: 1;
        background: $panel;
    }

    #topic-details {
        height: 30%;
        border: solid $panel;
        margin-top: 1;
        padding: 1;
        background: $surface;
    }

    .input-row {
        height: 3;
        margin-bottom: 1;
    }

    .input-row Label {
        width: 25%;
        content-align: right middle;
        padding-right: 1;
        color: $text-muted;
    }

    .input-row Input {
        width: 75%;
    }

    #button-row {
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    Button {
        margin: 1;
    }

    #priority-selector {
        height: 3;
        margin-bottom: 1;
    }

    #priority-selector Label {
        width: 25%;
        content-align: right middle;
        padding-right: 1;
        color: $text-muted;
    }

    #priority-selector Horizontal {
        width: 75%;
        align: left middle;
    }

    .priority-btn {
        width: 20%;
        margin: 1;
    }

    .priority-btn.high {
        background: $error;
        color: $text;
    }

    .priority-btn.medium {
        background: $warning;
        color: $text;
    }

    .priority-btn.low {
        background: $success;
        color: $text;
    }

    .priority-btn.selected {
        border: thick $primary;
    }

    #tags-input {
        height: 3;
        margin-bottom: 1;
    }

    #tags-input Label {
        width: 25%;
        content-align: right middle;
        padding-right: 1;
        color: $text-muted;
    }

    #tags-input Input {
        width: 75%;
    }

    .topic-item {
        padding: 1;
        border-bottom: solid $panel;
    }

    .topic-item:hover {
        background: $primary 20%;
    }

    .topic-item.selected {
        background: $primary 30%;
    }

    .topic-title {
        color: $text;
        text-style: bold;
    }

    .topic-meta {
        color: $text-muted;
        text-style: italic;
    }

    #status-bar {
        height: 1;
        margin-top: 1;
        color: $text-muted;
    }

    #topic-count {
        color: $text;
        text-style: bold;
    }

    #search-box {
        height: 3;
        margin-bottom: 1;
    }

    #search-box Label {
        width: 15%;
        content-align: right middle;
        padding-right: 1;
        color: $text-muted;
    }

    #search-box Input {
        width: 85%;
    }
    """

    def __init__(self):
        super().__init__()
        self.topics = []
        self.selected_topic = None
        self.selected_priority = "medium"
        self.data_file = "topics_data.json"
        self.load_topics()

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Container(
            Horizontal(
                # Left Panel - Topic List
                Container(
                    Label("📚 My Topics", id="panel-title"),
                    Horizontal(
                        Label("🔍 Search:"),
                        Input(placeholder="Filter topics...", id="search-input"),
                        id="search-box",
                    ),
                    ScrollableContainer(
                        ListView(id="topic-list"),
                        id="topic-list-container",
                    ),
                    Static("", id="status-bar"),
                    id="left-panel",
                ),
                # Right Panel - Input & Details
                Container(
                    Label("✏️ Add New Topic", id="panel-title"),
                    # Topic title input
                    Horizontal(
                        Label("Title:"),
                        Input(placeholder="Enter topic title...", id="title-input"),
                        classes="input-row",
                    ),
                    # Description input
                    Horizontal(
                        Label("Description:"),
                        Input(placeholder="Enter topic description...", id="desc-input"),
                        classes="input-row",
                    ),
                    # Priority selector
                    Container(
                        Label("Priority:"),
                        Horizontal(
                            Button("🔴 High", variant="error", id="priority-high", classes="priority-btn high"),
                            Button("🟡 Medium", variant="warning", id="priority-medium", classes="priority-btn medium selected"),
                            Button("🟢 Low", variant="success", id="priority-low", classes="priority-btn low"),
                        ),
                        id="priority-selector",
                    ),
                    # Tags input
                    Horizontal(
                        Label("Tags:"),
                        Input(placeholder="Comma-separated tags...", id="tags-input"),
                        id="tags-input",
                    ),
                    # Buttons
                    Horizontal(
                        Button("➕ Add Topic", variant="primary", id="add-btn"),
                        Button("🗑️ Delete", variant="error", id="delete-btn"),
                        Button("💾 Save", variant="success", id="save-btn"),
                        Button("📤 Export", variant="default", id="export-btn"),
                        id="button-row",
                    ),
                    # Topic details display
                    Container(
                        Label("📋 Topic Details", id="details-title"),
                        Static("Select a topic to view details", id="topic-details"),
                        id="details-container",
                    ),
                    id="right-panel",
                ),
                id="main-container",
            ),
        )
        yield Footer()

    def on_mount(self) -> None:
        """Set up the app when it starts."""
        self.title = "Topic Manager"
        self.refresh_topic_list()

    def load_topics(self) -> None:
        """Load topics from JSON file if it exists."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    self.topics = json.load(f)
            except:
                self.topics = []
        else:
            # Add sample topics
            self.topics = [
                {
                    "id": 1,
                    "title": "Python Programming",
                    "description": "Advanced Python concepts and best practices",
                    "priority": "high",
                    "tags": ["python", "programming", "development"],
                    "created": "2026-01-15 10:30:00",
                    "updated": "2026-01-15 10:30:00"
                },
                {
                    "id": 2,
                    "title": "Machine Learning",
                    "description": "Introduction to ML algorithms",
                    "priority": "medium",
                    "tags": ["ml", "ai", "data-science"],
                    "created": "2026-01-14 14:20:00",
                    "updated": "2026-01-14 14:20:00"
                }
            ]
            self.save_topics()

    def save_topics(self) -> None:
        """Save topics to JSON file."""
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.topics, f, indent=2)
        except:
            pass

    def refresh_topic_list(self) -> None:
        """Update the topic list view."""
        list_view = self.query_one("#topic-list", ListView)
        list_view.clear()
        
        search_term = self.query_one("#search-input", Input).value.lower()
        
        # Filter topics based on search
        filtered_topics = self.topics
        if search_term:
            filtered_topics = [
                t for t in self.topics 
                if search_term in t["title"].lower() or 
                   search_term in t["description"].lower() or
                   any(search_term in tag.lower() for tag in t["tags"])
            ]
        
        # Sort by priority (high -> medium -> low)
        priority_order = {"high": 0, "medium": 1, "low": 2}
        filtered_topics.sort(key=lambda x: priority_order.get(x["priority"], 3))
        
        for topic in filtered_topics:
            # Create a display string with priority indicator
            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            display_text = f"{priority_emoji.get(topic['priority'], '⚪')} {topic['title']}"
            if topic.get("tags"):
                display_text += f" [{' '.join(['#'+tag for tag in topic['tags'][:3]])}]"
            
            list_view.append(ListItem(Static(display_text)))
        
        # Update status
        status = self.query_one("#status-bar", Static)
        status.update(f"📊 Total: {len(self.topics)} topics | Showing: {len(filtered_topics)}")
        
        # Update details if no selection
        if not self.selected_topic and self.topics:
            self.select_topic(0)

    def select_topic(self, index: int) -> None:
        """Select and display a specific topic."""
        if 0 <= index < len(self.topics):
            self.selected_topic = index
            topic = self.topics[index]
            
            details = self.query_one("#topic-details", Static)
            details.update(
                f"📌 {topic['title']}\n\n"
                f"📝 {topic['description']}\n\n"
                f"⚡ Priority: {topic['priority'].upper()}\n"
                f"🏷️ Tags: {', '.join(topic.get('tags', []))}\n"
                f"📅 Created: {topic.get('created', 'N/A')}\n"
                f"🔄 Updated: {topic.get('updated', 'N/A')}"
            )
            
            # Update list selection
            list_view = self.query_one("#topic-list", ListView)
            list_view.index = index

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle topic selection from list."""
        if event.list_view.id == "topic-list":
            self.select_topic(event.index)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        button_id = event.button.id
        
        if button_id == "add-btn":
            self.add_topic()
        elif button_id == "delete-btn":
            self.delete_topic()
        elif button_id == "save-btn":
            self.save_topics()
            self.notify("💾 Topics saved successfully!", severity="information")
        elif button_id == "export-btn":
            self.export_topics()
        elif button_id in ["priority-high", "priority-medium", "priority-low"]:
            self.set_priority(button_id)

    def add_topic(self) -> None:
        """Add a new topic from input fields."""
        title = self.query_one("#title-input", Input).value.strip()
        description = self.query_one("#desc-input", Input).value.strip()
        tags_text = self.query_one("#tags-input", Input).value.strip()
        
        if not title:
            self.notify("⚠️ Please enter a topic title!", severity="error")
            return
        
        # Parse tags
        tags = [tag.strip().lower() for tag in tags_text.split(",") if tag.strip()]
        
        # Create new topic
        new_topic = {
            "id": len(self.topics) + 1,
            "title": title,
            "description": description,
            "priority": self.selected_priority,
            "tags": tags,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        self.topics.append(new_topic)
        self.save_topics()
        self.refresh_topic_list()
        
        # Clear inputs
        self.query_one("#title-input", Input).value = ""
        self.query_one("#desc-input", Input).value = ""
        self.query_one("#tags-input", Input).value = ""
        
        # Select new topic
        self.select_topic(len(self.topics) - 1)
        
        self.notify(f"✅ Topic '{title}' added successfully!", severity="information")

    def delete_topic(self) -> None:
        """Delete the selected topic."""
        if self.selected_topic is None or self.selected_topic >= len(self.topics):
            self.notify("⚠️ No topic selected to delete!", severity="warning")
            return
        
        topic_title = self.topics[self.selected_topic]["title"]
        del self.topics[self.selected_topic]
        self.save_topics()
        
        # Reset selection
        if self.topics:
            self.selected_topic = min(self.selected_topic, len(self.topics) - 1)
            self.select_topic(self.selected_topic)
        else:
            self.selected_topic = None
            self.query_one("#topic-details", Static).update("No topics available")
        
        self.refresh_topic_list()
        self.notify(f"🗑️ Topic '{topic_title}' deleted", severity="information")

    def set_priority(self, button_id: str) -> None:
        """Set the priority for new topics."""
        priority_map = {
            "priority-high": "high",
            "priority-medium": "medium",
            "priority-low": "low"
        }
        self.selected_priority = priority_map.get(button_id, "medium")
        
        # Update button styles
        for btn_id, priority in priority_map.items():
            btn = self.query_one(f"#{btn_id}", Button)
            if priority == self.selected_priority:
                btn.add_class("selected")
            else:
                btn.remove_class("selected")

    def export_topics(self) -> None:
        """Export topics to a text file."""
        if not self.topics:
            self.notify("⚠️ No topics to export!", severity="warning")
            return
        
        export_file = f"topics_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            with open(export_file, 'w') as f:
                f.write("=" * 60 + "\n")
                f.write("TOPIC EXPORT\n")
                f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")
                
                for i, topic in enumerate(self.topics, 1):
                    f.write(f"{i}. {topic['title']}\n")
                    f.write(f"   Description: {topic['description']}\n")
                    f.write(f"   Priority: {topic['priority'].upper()}\n")
                    f.write(f"   Tags: {', '.join(topic.get('tags', []))}\n")
                    f.write(f"   Created: {topic.get('created', 'N/A')}\n")
                    f.write(f"   Updated: {topic.get('updated', 'N/A')}\n")
                    f.write("-" * 60 + "\n")
            
            self.notify(f"📤 Exported {len(self.topics)} topics to {export_file}", severity="information")
        except Exception as e:
            self.notify(f"❌ Export failed: {str(e)}", severity="error")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key press in input fields."""
        if event.input.id == "search-input":
            self.refresh_topic_list()
        elif event.input.id in ["title-input", "desc-input", "tags-input"]:
            self.add_topic()


if __name__ == "__main__":
    app = TopicManager()
    app.run()
