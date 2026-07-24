"""
Knowledge Base Manager - Fully Working TUI Application
Fixed TabbedContent initialization
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer, Grid
from textual.widgets import (
    Header, Footer, Button, Input, Label, Static, ListView, ListItem,
    TextArea, TabbedContent, TabPane, Checkbox, ProgressBar
)
from textual.binding import Binding
from datetime import datetime
import json
import os


class KnowledgeBaseApp(App):
    """A feature-rich knowledge management TUI application."""
    
    CSS = """
    #main-container {
        height: 100%;
        padding: 1;
        background: $surface;
    }
    
    #stats-bar {
        height: 3;
        margin-bottom: 1;
        background: $primary 20%;
        padding: 1;
    }
    
    .stat-item {
        width: 25%;
        content-align: center middle;
        color: $text;
    }
    
    .stat-value {
        color: $primary;
        text-style: bold;
    }
    
    #main-panel {
        height: 100%;
    }
    
    #left-sidebar {
        width: 30%;
        height: 100%;
        border: solid $primary;
        padding: 1;
        margin-right: 1;
        background: $panel;
    }
    
    #right-content {
        width: 70%;
        height: 100%;
        border: solid $secondary;
        padding: 1;
        background: $surface;
    }
    
    #search-container {
        height: 3;
        margin-bottom: 1;
    }
    
    #search-container Input {
        width: 100%;
    }
    
    #topic-list {
        height: 60%;
        border: solid $panel;
        margin-top: 1;
        background: $surface;
    }
    
    #filter-container {
        height: 3;
        margin-top: 1;
    }
    
    .filter-btn {
        margin: 1;
        width: 20%;
    }
    
    .filter-btn.active {
        border: thick $primary;
        background: $primary 30%;
    }
    
    #input-section {
        height: 45%;
        border: solid $panel;
        padding: 1;
        margin-bottom: 1;
    }
    
    .input-row {
        height: 3;
        margin-bottom: 1;
    }
    
    .input-row Label {
        width: 20%;
        content-align: right middle;
        padding-right: 1;
        color: $text-muted;
    }
    
    .input-row Input {
        width: 80%;
    }
    
    #description-area {
        height: 6;
        margin-bottom: 1;
    }
    
    #description-area Label {
        width: 20%;
        content-align: right middle;
        padding-right: 1;
        color: $text-muted;
    }
    
    #description-area TextArea {
        width: 80%;
        height: 100%;
    }
    
    #tag-container {
        height: 3;
        margin-bottom: 1;
    }
    
    #tag-container Label {
        width: 20%;
        content-align: right middle;
        padding-right: 1;
        color: $text-muted;
    }
    
    #tag-container Input {
        width: 60%;
    }
    
    #tag-container Button {
        width: 10%;
    }
    
    #button-row {
        height: 3;
        align: center middle;
        margin-top: 1;
    }
    
    Button {
        margin: 1;
        min-width: 15;
    }
    
    #details-section {
        height: 45%;
        border: solid $panel;
        padding: 1;
        background: $surface;
    }
    
    #details-content {
        height: 100%;
        padding: 1;
        background: $panel;
    }
    
    #priority-selector {
        height: 3;
        margin-bottom: 1;
    }
    
    #priority-selector Label {
        width: 20%;
        content-align: right middle;
        padding-right: 1;
        color: $text-muted;
    }
    
    .priority-option {
        margin: 1;
        min-width: 10;
    }
    
    .priority-option.selected {
        border: thick $primary;
        background: $primary 30%;
    }
    
    .priority-option.high {
        background: $error;
        color: $text;
    }
    
    .priority-option.medium {
        background: $warning;
        color: $text;
    }
    
    .priority-option.low {
        background: $success;
        color: $text;
    }
    
    #status-bar {
        height: 1;
        margin-top: 1;
        color: $text-muted;
        padding: 1;
    }
    
    #analytics-panel {
        height: 100%;
        padding: 1;
    }
    
    .analytics-grid {
        grid-size: 2 2;
        grid-gutter: 1;
        height: 70%;
    }
    
    .analytics-card {
        border: solid $panel;
        padding: 1;
        background: $surface;
    }
    
    .analytics-card .title {
        color: $text-muted;
        text-style: italic;
    }
    
    .analytics-card .value {
        color: $primary;
        text-style: bold;
    }
    
    #tag-cloud {
        height: 30%;
        padding: 1;
    }
    
    .tag-chip {
        background: $primary 40%;
        color: $text;
        padding: 1;
        margin: 1;
    }
    
    .tag-chip:hover {
        background: $primary 60%;
    }
    
    #progress-container {
        margin: 1;
        height: 3;
    }
    
    #progress-container ProgressBar {
        width: 100%;
        height: 100%;
    }
    
    .quick-action-btn {
        margin: 1;
        min-width: 12;
    }
    
    .dim-text {
        color: $text-muted;
        text-style: italic;
    }
    
    .section-title {
        color: $text;
        text-style: bold;
        margin-bottom: 1;
    }
    
    .progress-section {
        margin: 1;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+n", "new_topic", "New Topic"),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+d", "delete", "Delete"),
        Binding("ctrl+f", "focus_search", "Search"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("escape", "clear_selection", "Clear"),
    ]
    
    def __init__(self):
        super().__init__()
        self.topics = []
        self.selected_topic_id = None
        self.current_filter = "all"
        self.selected_priority = "medium"
        self.tags = set()
        self.data_file = "knowledge_base.json"
        self.load_data()
        
    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header(show_clock=True)
        
        # Use TabbedContent without initial parameter to avoid ID issues
        with TabbedContent():
            # Topics Tab - use simple IDs without special characters
            with TabPane("📚 Topics", id="tab-topics"):
                with Container(id="main-container"):
                    # Stats bar
                    with Container(id="stats-bar"):
                        yield Horizontal(
                            Static("📚 Total: ", classes="stat-item"),
                            Static("0", id="total-count", classes="stat-item stat-value"),
                            Static("⭐ High: ", classes="stat-item"),
                            Static("0", id="priority-count", classes="stat-item stat-value"),
                            Static("🏷️ Tags: ", classes="stat-item"),
                            Static("0", id="tag-count", classes="stat-item stat-value"),
                            Static("📝 Recent: ", classes="stat-item"),
                            Static("0", id="recent-count", classes="stat-item stat-value"),
                        )
                    
                    with Horizontal(id="main-panel"):
                        # Left sidebar
                        with Vertical(id="left-sidebar"):
                            with Container(id="search-container"):
                                yield Input(placeholder="🔍 Search topics...", id="search-input")
                            
                            yield ScrollableContainer(
                                ListView(id="topic-list"),
                                id="topic-list-container",
                            )
                            
                            with Horizontal(id="filter-container"):
                                yield Button("All", id="filter-all", classes="filter-btn active")
                                yield Button("High", id="filter-high", classes="filter-btn")
                                yield Button("Medium", id="filter-medium", classes="filter-btn")
                                yield Button("Low", id="filter-low", classes="filter-btn")
                        
                        # Right content
                        with Vertical(id="right-content"):
                            with Container(id="input-section"):
                                yield Label("✏️ Add/Edit Topic", classes="section-title")
                                
                                with Horizontal(classes="input-row"):
                                    yield Label("Title:")
                                    yield Input(placeholder="Enter topic title...", id="title-input")
                                
                                with Container(id="description-area"):
                                    yield Label("Description:")
                                    yield TextArea(placeholder="Enter description...", id="desc-textarea")
                                
                                with Horizontal(id="priority-selector"):
                                    yield Label("Priority:")
                                    yield Button("🔴 High", id="priority-high", classes="priority-option high")
                                    yield Button("🟡 Medium", id="priority-medium", classes="priority-option medium selected")
                                    yield Button("🟢 Low", id="priority-low", classes="priority-option low")
                                
                                with Horizontal(id="tag-container"):
                                    yield Label("Tags:")
                                    yield Input(placeholder="tag1, tag2, ...", id="tag-input")
                                    yield Button("➕", id="add-tag-btn", variant="primary")
                                
                                with Horizontal(id="button-row"):
                                    yield Button("➕ Add", variant="primary", id="add-btn")
                                    yield Button("💾 Update", variant="warning", id="update-btn")
                                    yield Button("🗑️ Delete", variant="error", id="delete-btn")
                                    yield Button("📤 Export", variant="default", id="export-btn")
                            
                            with Container(id="details-section"):
                                yield Label("📋 Topic Details", classes="section-title")
                                yield ScrollableContainer(
                                    Static("Select a topic to view details", id="details-content"),
                                    id="details-scroll",
                                )
                            
                            yield Static("Ready - Press Ctrl+N for new topic", id="status-bar")
            
            # Analytics Tab
            with TabPane("📊 Analytics", id="tab-analytics"):
                with Container(id="analytics-panel"):
                    yield Label("📊 Analytics Dashboard", classes="section-title")
                    
                    with Grid(classes="analytics-grid"):
                        with Container(classes="analytics-card"):
                            yield Static("Total Topics", classes="title")
                            yield Static("0", id="analytics-total", classes="value")
                        
                        with Container(classes="analytics-card"):
                            yield Static("High Priority", classes="title")
                            yield Static("0", id="analytics-high", classes="value")
                        
                        with Container(classes="analytics-card"):
                            yield Static("Unique Tags", classes="title")
                            yield Static("0", id="analytics-tags", classes="value")
                        
                        with Container(classes="analytics-card"):
                            yield Static("Recent Topics", classes="title")
                            yield Static("0", id="analytics-recent", classes="value")
                    
                    with Container(id="tag-cloud"):
                        yield Label("🏷️ Tag Cloud", classes="section-title")
                        yield ScrollableContainer(id="tag-cloud-container")
                    
                    with Horizontal():
                        yield Button("📊 Export Analytics", id="export-analytics-btn", classes="quick-action-btn")
                        yield Button("🔄 Refresh Stats", id="refresh-stats-btn", classes="quick-action-btn")
            
            # Tags Tab
            with TabPane("🏷️ Tags", id="tab-tags"):
                with Container(id="analytics-panel"):
                    yield Label("🏷️ Tag Management", classes="section-title")
                    with Horizontal():
                        yield Input(placeholder="Tag name...", id="new-tag-input")
                        yield Button("➕ Add Tag", variant="primary", id="create-tag-btn")
                        yield Button("🗑️ Clear All", variant="error", id="clear-tags-btn")
                    
                    yield Label("Click a tag to filter topics", classes="dim-text")
                    yield ScrollableContainer(id="tag-list-container")
            
            # Settings Tab
            with TabPane("⚙️ Settings", id="tab-settings"):
                with Container(id="analytics-panel"):
                    yield Label("⚙️ Settings", classes="section-title")
                    yield Label("Data Management", classes="section-title")
                    
                    with Container():
                        with Horizontal():
                            yield Button("💾 Save Data", variant="success", id="settings-save-btn")
                            yield Button("🔄 Reset Data", variant="error", id="settings-reset-btn")
                            yield Button("📤 Export All", variant="default", id="settings-export-btn")
                    
                    yield Label("Preferences", classes="section-title")
                    yield Checkbox("Auto-save on change", id="auto-save-check", value=True)
                    yield Checkbox("Show notifications", id="notifications-check", value=True)
                    
                    yield Label("Data File: knowledge_base.json", classes="dim-text")
                    yield Label(f"Topics: {len(self.topics)}", id="settings-topic-count", classes="dim-text")
            
            # Progress Tab
            with TabPane("📈 Progress", id="tab-progress"):
                with Container(id="analytics-panel"):
                    yield Label("📈 Progress Tracking", classes="section-title")
                    
                    yield Label("Overall Knowledge Progress", classes="section-title")
                    with Container(id="progress-container"):
                        progress = ProgressBar(total=100)
                        progress.id = "overall-progress"
                        yield progress
                    
                    yield Label("Priority Distribution", classes="section-title")
                    with Horizontal():
                        with Container():
                            yield Label("High Priority")
                            p1 = ProgressBar(total=100)
                            p1.id = "high-progress"
                            yield p1
                        with Container():
                            yield Label("Medium Priority")
                            p2 = ProgressBar(total=100)
                            p2.id = "medium-progress"
                            yield p2
                        with Container():
                            yield Label("Low Priority")
                            p3 = ProgressBar(total=100)
                            p3.id = "low-progress"
                            yield p3
                    
                    yield Label("📊 Quick Stats", classes="section-title")
                    yield Static("", id="progress-stats")
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Set up the app when it starts."""
        self.title = "Knowledge Base Manager"
        self.sub_title = "Organize your knowledge effectively"
        self.refresh_all()
    
    def load_data(self) -> None:
        """Load data from JSON file."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.topics = data.get("topics", [])
                    self.update_tags()
            except:
                self.create_sample_data()
        else:
            self.create_sample_data()
    
    def create_sample_data(self) -> None:
        """Create sample topics for demonstration."""
        sample_topics = [
            {
                "id": 1,
                "title": "Python Best Practices",
                "description": "Writing clean, efficient, and maintainable Python code following PEP 8 guidelines.",
                "priority": "high",
                "tags": ["python", "programming", "best-practices"],
                "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                "id": 2,
                "title": "Machine Learning Fundamentals",
                "description": "Understanding core ML concepts: supervised, unsupervised, and reinforcement learning.",
                "priority": "high",
                "tags": ["ml", "ai", "data-science"],
                "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                "id": 3,
                "title": "Web Development with Flask",
                "description": "Building web applications using Flask framework with REST APIs and database integration.",
                "priority": "medium",
                "tags": ["web", "flask", "python"],
                "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            {
                "id": 4,
                "title": "Docker Containerization",
                "description": "Containerizing applications with Docker for consistent deployment and scaling.",
                "priority": "low",
                "tags": ["docker", "devops", "containers"],
                "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        ]
        self.topics = sample_topics
        self.update_tags()
        self.save_data()
    
    def save_data(self) -> None:
        """Save data to JSON file."""
        try:
            data = {"topics": self.topics}
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.notify(f"❌ Save failed: {str(e)}", severity="error")
    
    def update_tags(self) -> None:
        """Update the global tags set."""
        self.tags = set()
        for topic in self.topics:
            self.tags.update(topic.get("tags", []))
    
    def refresh_topic_list(self) -> None:
        """Refresh the topic list view."""
        list_view = self.query_one("#topic-list", ListView)
        list_view.clear()
        
        search_term = self.query_one("#search-input", Input).value.lower().strip()
        filtered_topics = self.get_filtered_topics(search_term)
        
        for topic in filtered_topics:
            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            display_text = f"{priority_emoji.get(topic['priority'], '⚪')} {topic['title']}"
            if topic.get("tags"):
                display_text += f" [{' '.join(['#'+tag for tag in topic['tags'][:3]])}]"
            
            list_view.append(ListItem(Static(display_text)))
        
        self.update_stats(len(self.topics), len(filtered_topics))
        self.query_one("#status-bar", Static).update(f"📊 Showing {len(filtered_topics)} of {len(self.topics)} topics")
    
    def get_filtered_topics(self, search_term: str = "") -> list:
        """Get topics based on current filter and search term."""
        filtered = self.topics
        
        if self.current_filter != "all":
            filtered = [t for t in filtered if t["priority"] == self.current_filter]
        
        if search_term:
            filtered = [
                t for t in filtered
                if search_term in t["title"].lower() or
                   search_term in t["description"].lower() or
                   any(search_term in tag.lower() for tag in t.get("tags", []))
            ]
        
        priority_order = {"high": 0, "medium": 1, "low": 2}
        filtered.sort(key=lambda x: (priority_order.get(x["priority"], 3), x["title"].lower()))
        
        return filtered
    
    def update_stats(self, total: int, shown: int) -> None:
        """Update the stats bar."""
        self.query_one("#total-count", Static).update(str(total))
        
        high_count = sum(1 for t in self.topics if t["priority"] == "high")
        self.query_one("#priority-count", Static).update(str(high_count))
        
        self.query_one("#tag-count", Static).update(str(len(self.tags)))
        
        # Recent topics (last 7 days)
        recent_count = sum(1 for t in self.topics 
                          if (datetime.now() - datetime.strptime(t.get("created", datetime.now().strftime("%Y-%m-%d %H:%M:%S")), 
                                                              "%Y-%m-%d %H:%M:%S")).days < 7)
        self.query_one("#recent-count", Static).update(str(recent_count))
    
    def display_topic_details(self, topic_id: int) -> None:
        """Display details of a selected topic."""
        topic = next((t for t in self.topics if t["id"] == topic_id), None)
        if not topic:
            return
        
        details = self.query_one("#details-content", Static)
        detail_text = f"""📌 {topic['title']}

📝 Description:
   {topic['description']}

⚡ Priority: {topic['priority'].upper()}
🏷️ Tags: {', '.join(topic.get('tags', [])) or 'None'}
📅 Created: {topic.get('created', 'N/A')}
🔄 Updated: {topic.get('updated', 'N/A')}"""
        
        details.update(detail_text)
    
    def select_topic(self, index: int) -> None:
        """Select a topic from the list."""
        if index < 0:
            return
        
        list_view = self.query_one("#topic-list", ListView)
        filtered = self.get_filtered_topics(
            self.query_one("#search-input", Input).value.lower().strip()
        )
        
        if index < len(filtered):
            topic = filtered[index]
            self.selected_topic_id = topic["id"]
            list_view.index = index
            self.display_topic_details(topic["id"])
            
            self.query_one("#title-input", Input).value = topic["title"]
            self.query_one("#desc-textarea", TextArea).text = topic["description"]
            self.set_priority_display(topic["priority"])
            self.query_one("#tag-input", Input).value = ", ".join(topic.get("tags", []))
    
    def set_priority_display(self, priority: str) -> None:
        """Update priority button display."""
        self.selected_priority = priority
        for btn_id, p in [("priority-high", "high"), ("priority-medium", "medium"), ("priority-low", "low")]:
            btn = self.query_one(f"#{btn_id}", Button)
            if p == priority:
                btn.add_class("selected")
            else:
                btn.remove_class("selected")
    
    def add_topic(self) -> None:
        """Add a new topic."""
        title = self.query_one("#title-input", Input).value.strip()
        description = self.query_one("#desc-textarea", TextArea).text.strip()
        tags_text = self.query_one("#tag-input", Input).value.strip()
        
        if not title:
            self.notify("⚠️ Please enter a topic title!", severity="error")
            return
        
        tags = [tag.strip().lower() for tag in tags_text.split(",") if tag.strip()]
        
        new_topic = {
            "id": max([t["id"] for t in self.topics] + [0]) + 1,
            "title": title,
            "description": description,
            "priority": self.selected_priority,
            "tags": tags,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        self.topics.append(new_topic)
        self.update_tags()
        self.save_data()
        self.clear_inputs()
        self.refresh_all()
        self.notify(f"✅ Topic '{title}' added!", severity="information")
    
    def update_topic(self) -> None:
        """Update the selected topic."""
        if not self.selected_topic_id:
            self.notify("⚠️ No topic selected!", severity="warning")
            return
        
        title = self.query_one("#title-input", Input).value.strip()
        description = self.query_one("#desc-textarea", TextArea).text.strip()
        tags_text = self.query_one("#tag-input", Input).value.strip()
        
        if not title:
            self.notify("⚠️ Please enter a topic title!", severity="error")
            return
        
        for topic in self.topics:
            if topic["id"] == self.selected_topic_id:
                topic["title"] = title
                topic["description"] = description
                topic["priority"] = self.selected_priority
                topic["tags"] = [tag.strip().lower() for tag in tags_text.split(",") if tag.strip()]
                topic["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                break
        
        self.update_tags()
        self.save_data()
        self.refresh_all()
        self.notify(f"✅ Topic '{title}' updated!", severity="information")
    
    def delete_topic(self) -> None:
        """Delete the selected topic."""
        if not self.selected_topic_id:
            self.notify("⚠️ No topic selected!", severity="warning")
            return
        
        topic = next((t for t in self.topics if t["id"] == self.selected_topic_id), None)
        if not topic:
            return
        
        self.topics = [t for t in self.topics if t["id"] != self.selected_topic_id]
        self.update_tags()
        self.save_data()
        self.selected_topic_id = None
        self.clear_inputs()
        self.refresh_all()
        self.notify(f"🗑️ Topic '{topic['title']}' deleted", severity="information")
    
    def clear_inputs(self) -> None:
        """Clear all input fields."""
        self.query_one("#title-input", Input).value = ""
        self.query_one("#desc-textarea", TextArea).text = ""
        self.query_one("#tag-input", Input).value = ""
        self.query_one("#details-content", Static).update("Select a topic to view details")
        self.set_priority_display("medium")
    
    def refresh_all(self) -> None:
        """Refresh all components."""
        self.refresh_topic_list()
        self.update_analytics()
        self.update_tags_view()
        self.update_progress()
        
        if not self.topics:
            self.query_one("#details-content", Static).update("No topics available")
    
    def update_analytics(self) -> None:
        """Update the analytics dashboard."""
        try:
            total = len(self.topics)
            high = sum(1 for t in self.topics if t["priority"] == "high")
            tags = len(self.tags)
            recent = sorted(self.topics, key=lambda x: x.get("created", ""), reverse=True)[:3]
            
            self.query_one("#analytics-total", Static).update(str(total))
            self.query_one("#analytics-high", Static).update(str(high))
            self.query_one("#analytics-tags", Static).update(str(tags))
            self.query_one("#analytics-recent", Static).update(str(len(recent)))
        except:
            pass
    
    def update_tags_view(self) -> None:
        """Update the tags management view."""
        try:
            container = self.query_one("#tag-list-container", ScrollableContainer)
            container.remove_children()
            
            for tag in sorted(self.tags):
                count = sum(1 for t in self.topics if tag in t.get("tags", []))
                container.mount(
                    Horizontal(
                        Static(f"🏷️ {tag}", classes="tag-chip"),
                        Static(f"({count} topics)"),
                        Button("🗑️", id=f"delete-tag-{tag}", variant="error"),
                    )
                )
        except:
            pass
    
    def update_progress(self) -> None:
        """Update the progress tracking view."""
        try:
            if not self.topics:
                return
            
            total_tags = sum(len(t.get("tags", [])) for t in self.topics)
            avg_tags = total_tags / len(self.topics) if self.topics else 0
            progress_value = min(100, (avg_tags / 5) * 100)
            
            # Set progress bar values
            self.query_one("#overall-progress", ProgressBar).progress = progress_value
            
            total = len(self.topics)
            high_count = sum(1 for t in self.topics if t["priority"] == "high")
            medium_count = sum(1 for t in self.topics if t["priority"] == "medium")
            low_count = sum(1 for t in self.topics if t["priority"] == "low")
            
            self.query_one("#high-progress", ProgressBar).progress = (high_count / total) * 100 if total > 0 else 0
            self.query_one("#medium-progress", ProgressBar).progress = (medium_count / total) * 100 if total > 0 else 0
            self.query_one("#low-progress", ProgressBar).progress = (low_count / total) * 100 if total > 0 else 0
            
            stats = f"High: {high_count} | Medium: {medium_count} | Low: {low_count}\nAvg Tags: {avg_tags:.1f} per topic"
            self.query_one("#progress-stats", Static).update(stats)
        except:
            pass
    
    def export_topics(self) -> None:
        """Export topics to markdown file."""
        if not self.topics:
            self.notify("⚠️ No topics to export!", severity="warning")
            return
        
        export_file = f"knowledge_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        try:
            with open(export_file, 'w') as f:
                f.write("# Knowledge Base Export\n\n")
                f.write(f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"**Total Topics:** {len(self.topics)}\n\n---\n\n")
                
                for i, topic in enumerate(self.topics, 1):
                    f.write(f"## {i}. {topic['title']}\n\n")
                    f.write(f"**Priority:** {topic['priority'].upper()}\n\n")
                    f.write(f"**Description:**\n{topic['description']}\n\n")
                    f.write(f"**Tags:** {', '.join(topic.get('tags', []))}\n\n")
                    f.write(f"**Created:** {topic.get('created', 'N/A')}\n")
                    f.write(f"**Updated:** {topic.get('updated', 'N/A')}\n\n---\n\n")
            
            self.notify(f"📤 Exported to {export_file}", severity="information")
        except Exception as e:
            self.notify(f"❌ Export failed: {str(e)}", severity="error")
    
    def export_analytics(self) -> None:
        """Export analytics report."""
        report_file = f"analytics_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            with open(report_file, 'w') as f:
                f.write("ANALYTICS REPORT\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total Topics: {len(self.topics)}\n")
                f.write(f"Unique Tags: {len(self.tags)}\n\n")
                
                f.write("Priority Distribution:\n")
                for priority in ["high", "medium", "low"]:
                    count = sum(1 for t in self.topics if t["priority"] == priority)
                    percentage = (count / len(self.topics) * 100) if self.topics else 0
                    f.write(f"  {priority.upper()}: {count} ({percentage:.1f}%)\n")
                
                f.write("\nTag Usage:\n")
                tag_counts = {}
                for topic in self.topics:
                    for tag in topic.get("tags", []):
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1
                for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                    f.write(f"  {tag}: {count} topics\n")
            
            self.notify(f"📊 Analytics exported to {report_file}", severity="information")
        except Exception as e:
            self.notify(f"❌ Export failed: {str(e)}", severity="error")
    
    def export_all_data(self) -> None:
        """Export all data including analytics."""
        export_file = f"full_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            data = {
                "topics": self.topics,
                "metadata": {
                    "exported": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total_topics": len(self.topics),
                    "total_tags": len(self.tags),
                    "version": "1.0"
                }
            }
            with open(export_file, 'w') as f:
                json.dump(data, f, indent=2)
            self.notify(f"📤 Full export saved to {export_file}", severity="information")
        except Exception as e:
            self.notify(f"❌ Export failed: {str(e)}", severity="error")
    
    # Event Handlers
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "topic-list":
            self.select_topic(event.index)
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search-input":
            self.refresh_topic_list()
        elif event.input.id == "title-input":
            self.add_topic()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        
        if button_id == "add-btn":
            self.add_topic()
        elif button_id == "update-btn":
            self.update_topic()
        elif button_id == "delete-btn":
            self.delete_topic()
        elif button_id == "export-btn":
            self.export_topics()
        elif button_id in ["priority-high", "priority-medium", "priority-low"]:
            priority_map = {"priority-high": "high", "priority-medium": "medium", "priority-low": "low"}
            self.set_priority_display(priority_map[button_id])
        elif button_id in ["filter-all", "filter-high", "filter-medium", "filter-low"]:
            self.current_filter = button_id.replace("filter-", "")
            for btn in ["filter-all", "filter-high", "filter-medium", "filter-low"]:
                b = self.query_one(f"#{btn}", Button)
                if btn == button_id:
                    b.add_class("active")
                else:
                    b.remove_class("active")
            self.refresh_topic_list()
        elif button_id == "settings-save-btn":
            self.save_data()
            self.notify("💾 Data saved!", severity="information")
        elif button_id == "settings-reset-btn":
            self.topics = []
            self.update_tags()
            self.save_data()
            self.refresh_all()
            self.notify("🔄 Data reset!", severity="information")
        elif button_id == "settings-export-btn":
            self.export_all_data()
        elif button_id == "create-tag-btn":
            self.create_tag()
        elif button_id == "clear-tags-btn":
            self.clear_all_tags()
        elif button_id.startswith("delete-tag-"):
            tag = button_id.replace("delete-tag-", "")
            self.delete_tag(tag)
        elif button_id == "export-analytics-btn":
            self.export_analytics()
        elif button_id == "refresh-stats-btn":
            self.update_analytics()
            self.notify("🔄 Stats refreshed!", severity="information")
        elif button_id == "add-tag-btn":
            self.add_tag_to_current()
    
    def add_tag_to_current(self) -> None:
        """Add a tag to the current topic's tag input."""
        tag_input = self.query_one("#tag-input", Input)
        current = tag_input.value.strip()
        if current:
            tag_input.value = current + ", new-tag"
        else:
            tag_input.value = "new-tag"
        self.notify("➕ Tag added", severity="information")
    
    def create_tag(self) -> None:
        """Create a new tag globally."""
        tag_input = self.query_one("#new-tag-input", Input)
        tag = tag_input.value.strip().lower()
        if tag and tag not in self.tags:
            self.tags.add(tag)
            self.update_tags_view()
            tag_input.value = ""
            self.notify(f"✅ Tag '{tag}' created!", severity="information")
        elif tag in self.tags:
            self.notify("⚠️ Tag already exists!", severity="warning")
        else:
            self.notify("⚠️ Please enter a tag name!", severity="warning")
    
    def delete_tag(self, tag: str) -> None:
        """Delete a tag from all topics."""
        if tag in self.tags:
            for topic in self.topics:
                if tag in topic.get("tags", []):
                    topic["tags"].remove(tag)
            self.update_tags()
            self.save_data()
            self.refresh_all()
            self.notify(f"🗑️ Tag '{tag}' deleted", severity="information")
    
    def clear_all_tags(self) -> None:
        """Clear all tags from all topics."""
        for topic in self.topics:
            topic["tags"] = []
        self.update_tags()
        self.save_data()
        self.refresh_all()
        self.notify("🗑️ All tags cleared!", severity="information")
    
    # Actions
    def action_new_topic(self) -> None:
        self.clear_inputs()
        self.query_one("#title-input", Input).focus()
        self.notify("📝 Enter new topic details", severity="information")
    
    def action_save(self) -> None:
        self.save_data()
        self.notify("💾 Data saved!", severity="information")
    
    def action_delete(self) -> None:
        self.delete_topic()
    
    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()
    
    def action_quit(self) -> None:
        self.exit()
    
    def action_clear_selection(self) -> None:
        self.selected_topic_id = None
        self.clear_inputs()
        self.query_one("#topic-list", ListView).index = None
        self.notify("Selection cleared", severity="information")


if __name__ == "__main__":
    app = KnowledgeBaseApp()
    app.run()
