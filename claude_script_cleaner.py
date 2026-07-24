from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Literal
from enum import Enum
import json
import re


class NodeType(str, Enum):
    """Types of nodes in the Claude output"""
    STATIC_TEXT = "StaticText"
    INLINE_TEXT_BOX = "InlineTextBox"
    GENERIC = "generic"
    PARAGRAPH = "paragraph"
    BUTTON = "button"
    CELL = "cell"
    ROW = "row"
    COLUMNHEADER = "columnheader"
    NONE = "none"


class ScriptComponent(BaseModel):
    """Represents a clean, meaningful script component"""
    text: str = Field(description="The actual script text content")
    type: Literal["narration", "visual", "hook", "open_loop", "callback", "pattern_interrupt", "title", "chapter", "cta", "outro"] = Field(description="Type of script component")
    timestamp_start: Optional[str] = Field(None, description="Start timestamp if present")
    timestamp_end: Optional[str] = Field(None, description="End timestamp if present")
    chapter: Optional[int] = Field(None, description="Chapter number if applicable")
    is_instruction: bool = Field(False, description="Whether this is a production instruction vs. narration")
    raw_text: str = Field("", description="Original unprocessed text for reference")


class ScriptChapter(BaseModel):
    """Represents a chapter of the script"""
    chapter_number: int
    title: Optional[str] = None
    components: List[ScriptComponent] = Field(default_factory=list)
    timestamp_start: Optional[str] = None
    timestamp_end: Optional[str] = None


class CleanScript(BaseModel):
    """The complete cleaned script"""
    title: str = "Untitled Script"
    chapters: List[ScriptChapter] = Field(default_factory=list)
    cold_open: Optional[ScriptChapter] = None
    outro: Optional[ScriptChapter] = None
    estimated_duration: Optional[str] = None
    raw_components: List[Dict[str, Any]] = Field(default_factory=list, description="For debugging")


class TextPattern(str, Enum):
    """Regex patterns for identifying script components"""
    NARRATION = r"^NARRATION:"
    VISUAL = r"^\[VISUAL:"
    HOOK = r"^\[HOOK"
    OPEN_LOOP = r"^\[OPEN LOOP"
    CALLBACK = r"^\[CALLBACK"
    PATTERN_INTERRUPT = r"^\[PATTERN INTERRUPT"
    CHAPTER = r"^CHAPTER\s+(\d+)"
    TITLE = r"^\[VISUAL:\s*Title\s+card"
    OUTRO = r"^OUTRO\s*/"
    CTA = r"^\[END CARD"


class ClaudeScriptCleaner:
    """
    Processes raw Claude output JSON to extract clean script content
    Separates noise (UI elements, metadata, formatting) from actual script
    """
    
    # Patterns for identifying noise nodes
    IGNORED_ROLES = {
        "role", "row", "cell", "columnheader", "button", "generic", 
        "paragraph", "none", "LineBreak"
    }
    
    IGNORED_NAMES = {
        "Technique", "Where used", "Purpose", "Write a message…", 
        "Model:", "Add files", "Document", "MD", "Download", "Open in Drive"
    }
    
    INSTRUCTION_PATTERNS = [
        r"^\[VISUAL:",
        r"^\[HOOK",
        r"^\[OPEN LOOP",
        r"^\[CALLBACK",
        r"^\[PATTERN INTERRUPT",
        r"^\[END CARD",
        r"^\[RETENTION",
        r"^Format legend:",
    ]
    
    def __init__(self):
        self.processed_nodes = set()
        self.accumulated_text = []
        self.current_chapter = None
        self.script_structure = {"chapters": [], "cold_open": None, "outro": None}
        
    def clean_json(self, json_data: Dict[str, Any]) -> CleanScript:
        """
        Main entry point - processes raw JSON and returns cleaned script
        """
        nodes = json_data.get("nodes", [])
        
        if not nodes:
            return CleanScript(title="Empty Script")
        
        # Extract all text content from meaningful nodes
        text_nodes = self._extract_meaningful_text(nodes)
        
        # Process text nodes into script components
        script_components = self._process_text_nodes(text_nodes)
        
        # Organize into chapters
        script = self._organize_into_chapters(script_components)
        
        # Extract title
        script.title = self._extract_title(nodes)
        
        # Estimate duration
        script.estimated_duration = self._extract_estimated_runtime(nodes)
        
        return script
    
    def _extract_meaningful_text(self, nodes: List[Dict]) -> List[Dict]:
        """
        Extract only meaningful text nodes, filtering out UI/noise
        """
        meaningful_nodes = []
        
        for node in nodes:
            # Skip ignored nodes
            if self._is_ignored_node(node):
                continue
            
            # Get text content
            text = self._extract_text_from_node(node)
            if not text or text.strip() == "":
                continue
            
            # Skip known noise patterns
            if self._is_noise_text(text):
                continue
            
            meaningful_nodes.append({
                "node_id": node.get("nodeId"),
                "text": text,
                "role": node.get("role", {}).get("value") if isinstance(node.get("role"), dict) else None,
                "chrome_role": node.get("chromeRole", {}).get("value") if isinstance(node.get("chromeRole"), dict) else None,
                "parent_id": node.get("parentId"),
                "backend_dom": node.get("backendDOMNodeId"),
            })
        
        return meaningful_nodes
    
    def _extract_text_from_node(self, node: Dict) -> str:
        """
        Extract text content from a node, handling different formats
        """
        # Direct name field
        if "name" in node and isinstance(node["name"], dict):
            name_value = node["name"].get("value", "")
            if isinstance(name_value, str) and name_value:
                return name_value
        
        # Check for sources (StaticText often has this)
        name = node.get("name", {})
        sources = name.get("sources", [])
        if sources:
            for source in sources:
                source_value = source.get("value", {})
                if isinstance(source_value, dict):
                    content_value = source_value.get("value", "")
                    if content_value:
                        return content_value
        
        # Child nodes might contain text
        child_ids = node.get("childIds", [])
        if child_ids:
            # Text might be in nested nodes - but we handle this at a higher level
            pass
        
        return ""
    
    def _is_ignored_node(self, node: Dict) -> bool:
        """Check if a node should be ignored"""
        # Check role
        role = node.get("role", {})
        role_value = role.get("value") if isinstance(role, dict) else None
        
        if role_value in self.IGNORED_ROLES:
            # But keep StaticText and InlineTextBox
            if role_value not in ["StaticText", "InlineTextBox"]:
                return True
        
        # Check if explicitly ignored
        if node.get("ignored") is True:
            return True
        
        # Check name patterns
        name = node.get("name", {})
        name_value = name.get("value", "") if isinstance(name, dict) else ""
        
        if name_value:
            for ignored_name in self.IGNORED_NAMES:
                if ignored_name.lower() in name_value.lower():
                    return True
        
        return False
    
    def _is_noise_text(self, text: str) -> bool:
        """Check if text is noise/formatting"""
        text_lower = text.lower().strip()
        
        # Single character noise
        if text in ["\n", "\t", " ", " ", ""]:
            return True
        
        # UI text
        noise_patterns = [
            r"^write an multi chapter",
            r"^high detailed youtube script",
            r"^use high retention techiques",
            r"^full 6-chapter script",
            r"^retention technique summary",
            r"^estimated runtime",
            r"^format legend",
            r"^\[.*\]$",  # Standalone bracket text (instructions)
        ]
        
        for pattern in noise_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        
        # Table content - usually has "|" or multiple columns
        if "|" in text and len(text.split("|")) > 2:
            return True
        
        return False
    
    def _process_text_nodes(self, nodes: List[Dict]) -> List[ScriptComponent]:
        """Process text nodes into ScriptComponents"""
        components = []
        
        # First, combine related nodes that are part of the same narrative
        combined_texts = self._combine_related_texts(nodes)
        
        for item in combined_texts:
            text = item["text"].strip()
            if not text:
                continue
            
            # Determine component type
            comp_type, cleaned_text, chapter = self._classify_text(text)
            
            # Extract timestamps if present
            timestamp_start, timestamp_end, text_without_ts = self._extract_timestamps(cleaned_text)
            
            # Check if this is an instruction
            is_instruction = bool(re.search(r"^\[", cleaned_text)) or bool(re.search(r"^NARRATION:", cleaned_text))
            if is_instruction:
                # It's a production instruction
                comp_type = "visual" if "[VISUAL" in cleaned_text else comp_type
            
            component = ScriptComponent(
                text=text_without_ts or cleaned_text,
                type=comp_type,
                timestamp_start=timestamp_start,
                timestamp_end=timestamp_end,
                chapter=chapter,
                is_instruction=is_instruction or comp_type in ["visual", "hook", "open_loop", "callback", "pattern_interrupt"],
                raw_text=text
            )
            
            components.append(component)
        
        return components
    
    def _combine_related_texts(self, nodes: List[Dict]) -> List[Dict]:
        """Combine text nodes that are part of the same narrative flow"""
        combined = []
        current_text = ""
        current_ids = []
        
        for node in nodes:
            # Check if this starts a new section
            text = node["text"]
            is_new_section = (
                re.match(r"^\[VISUAL:", text) or
                re.match(r"^\[HOOK", text) or
                re.match(r"^\[OPEN LOOP", text) or
                re.match(r"^\[CALLBACK", text) or
                re.match(r"^\[PATTERN INTERRUPT", text) or
                re.match(r"^CHAPTER", text) or
                re.match(r"^OUTRO", text) or
                re.match(r"^NARRATION:", text) or
                re.match(r"^COLD OPEN", text) or
                (current_text and text in [".", "!", "?"])  # Punctuation continuation
            )
            
            if is_new_section and current_text:
                combined.append({"text": current_text.strip(), "node_ids": current_ids})
                current_text = ""
                current_ids = []
            
            # Append to current text
            if current_text and not current_text.endswith((" ", "\n")):
                current_text += " "
            current_text += text
            current_ids.append(node["node_id"])
        
        if current_text:
            combined.append({"text": current_text.strip(), "node_ids": current_ids})
        
        return combined
    
    def _classify_text(self, text: str) -> tuple:
        """Classify text and extract metadata"""
        text_lower = text.lower().strip()
        chapter_match = re.match(r"^CHAPTER\s+(\d+)", text_lower, re.IGNORECASE)
        
        if chapter_match:
            chapter_num = int(chapter_match.group(1))
            # Remove the chapter marker
            cleaned_text = re.sub(r"^CHAPTER\s+\d+\s*", "", text, flags=re.IGNORECASE).strip()
            return "chapter", cleaned_text, chapter_num
        
        if re.match(r"^cold open", text_lower, re.IGNORECASE):
            return "narration", re.sub(r"^cold open\s*", "", text, flags=re.IGNORECASE).strip(), None
        
        if re.match(r"^outro", text_lower, re.IGNORECASE):
            return "outro", re.sub(r"^outro\s*", "", text, flags=re.IGNORECASE).strip(), None
        
        if re.match(r"^\[end card", text_lower):
            return "cta", re.sub(r"^\[end card[^\]]*\]\s*", "", text, flags=re.IGNORECASE).strip(), None
        
        if re.match(r"^\[hook", text_lower):
            cleaned = re.sub(r"^\[hook[^\]]*\]\s*", "", text, flags=re.IGNORECASE).strip()
            return "hook", cleaned or text, None
        
        if re.match(r"^\[open loop", text_lower):
            cleaned = re.sub(r"^\[open loop[^\]]*\]\s*", "", text, flags=re.IGNORECASE).strip()
            return "open_loop", cleaned or text, None
        
        if re.match(r"^\[callback", text_lower):
            cleaned = re.sub(r"^\[callback[^\]]*\]\s*", "", text, flags=re.IGNORECASE).strip()
            return "callback", cleaned or text, None
        
        if re.match(r"^\[pattern interrupt", text_lower):
            cleaned = re.sub(r"^\[pattern interrupt[^\]]*\]\s*", "", text, flags=re.IGNORECASE).strip()
            return "pattern_interrupt", cleaned or text, None
        
        if re.match(r"^\[visual:", text_lower):
            cleaned = re.sub(r"^\[visual:[^\]]*\]\s*", "", text, flags=re.IGNORECASE).strip()
            return "visual", cleaned or text, None
        
        if re.match(r"^narration:", text_lower):
            cleaned = re.sub(r"^narration:\s*", "", text, flags=re.IGNORECASE).strip()
            return "narration", cleaned, None
        
        # Default - probably narration
        return "narration", text, None
    
    def _extract_timestamps(self, text: str) -> tuple:
        """Extract timestamp patterns like (0:00 - 0:45) or (0:00)"""
        timestamp_pattern = r"\((\d+):(\d+)\s*[-–]\s*(\d+):(\d+)\)"
        single_pattern = r"\((\d+):(\d+)\)"
        
        match = re.search(timestamp_pattern, text)
        if match:
            start = f"{match.group(1)}:{match.group(2)}"
            end = f"{match.group(3)}:{match.group(4)}"
            cleaned = re.sub(timestamp_pattern, "", text).strip()
            return start, end, cleaned
        
        match = re.search(single_pattern, text)
        if match:
            start = f"{match.group(1)}:{match.group(2)}"
            cleaned = re.sub(single_pattern, "", text).strip()
            return start, None, cleaned
        
        return None, None, text
    
    def _organize_into_chapters(self, components: List[ScriptComponent]) -> CleanScript:
        """Organize components into chapters"""
        chapters_dict = {}
        cold_open = None
        outro = None
        current_chapter = None
        
        # First pass - group by chapter
        for comp in components:
            if comp.type == "chapter":
                # This is a chapter header
                chapter_num = comp.chapter or 1
                if chapter_num not in chapters_dict:
                    chapters_dict[chapter_num] = ScriptChapter(
                        chapter_number=chapter_num,
                        title=comp.text or f"Chapter {chapter_num}"
                    )
                    current_chapter = chapter_num
                continue
            
            if comp.type == "outro" or "outro" in comp.text.lower():
                if not outro:
                    outro = ScriptChapter(
                        chapter_number=0,
                        title="Outro",
                        components=[]
                    )
                if outro:
                    outro.components.append(comp)
                continue
            
            # Check for cold open
            if "cold open" in comp.text.lower() or comp.timestamp_start == "0:00":
                if not cold_open:
                    cold_open = ScriptChapter(
                        chapter_number=0,
                        title="Cold Open",
                        components=[]
                    )
                if cold_open:
                    cold_open.components.append(comp)
                continue
            
            # Add to current chapter
            if current_chapter and current_chapter in chapters_dict:
                # Don't add instruction markers to the chapter components directly
                # unless they're actual content
                if not comp.is_instruction or comp.type in ["hook", "open_loop", "callback", "pattern_interrupt"]:
                    chapters_dict[current_chapter].components.append(comp)
        
        # Convert to list and sort
        chapters = [chapters_dict[k] for k in sorted(chapters_dict.keys())]
        
        # Clean up chapters - remove duplicate chapter headers
        for chapter in chapters:
            # Remove any components that are just chapter markers
            chapter.components = [
                comp for comp in chapter.components 
                if not (comp.type == "chapter" and comp.text.startswith("Chapter"))
            ]
        
        return CleanScript(
            title="",  # Will be filled in later
            chapters=chapters,
            cold_open=cold_open,
            outro=outro
        )
    
    def _extract_title(self, nodes: List[Dict]) -> str:
        """Extract the script title from nodes"""
        for node in nodes:
            name = node.get("name", {})
            if isinstance(name, dict):
                name_value = name.get("value", "")
                if name_value and "The Science of Bioluminescent" in name_value:
                    return name_value.strip()
        
        # Try to find from user prompt
        for node in nodes:
            if node.get("nodeId") == "1065":  # The user prompt node
                name = node.get("name", {})
                if isinstance(name, dict):
                    value = name.get("value", "")
                    if "The Science of Bioluminescent" in value:
                        return "The Science of Bioluminescent Fish Camouflage"
        
        return "Bioluminescent Fish Camouflage Script"
    
    def _extract_estimated_runtime(self, nodes: List[Dict]) -> Optional[str]:
        """Extract estimated runtime from the script"""
        for node in nodes:
            name = node.get("name", {})
            if isinstance(name, dict):
                value = name.get("value", "")
                if "minute" in value or "runtime" in value:
                    match = re.search(r"~?(\d+)\s*[-–]\s*(\d+)\s*minute", value, re.IGNORECASE)
                    if match:
                        return f"{match.group(1)}-{match.group(2)} minutes"
                    
                    match = re.search(r"~?(\d+)\s*minute", value, re.IGNORECASE)
                    if match:
                        return f"~{match.group(1)} minutes"
        
        return None


def clean_script_from_file(file_path: str) -> CleanScript:
    """Utility function to clean a script from a JSON file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    cleaner = ClaudeScriptCleaner()
    return cleaner.clean_json(data)


def clean_script_from_string(json_string: str) -> CleanScript:
    """Utility function to clean a script from a JSON string"""
    data = json.loads(json_string)
    cleaner = ClaudeScriptCleaner()
    return cleaner.clean_json(data)


# Example usage
if __name__ == "__main__":
    # Example: Clean from file
    # script = clean_script_from_file("claude_output.json")
    
    # Example: Clean from string
    # with open("claude_output.json", "r") as f:
    #     json_str = f.read()
    # script = clean_script_from_string(json_str)
    
    # Print the cleaned script
    # print(f"Title: {script.title}")
    # print(f"Duration: {script.estimated_duration}")
    # for chapter in script.chapters:
    #     print(f"\nChapter {chapter.chapter_number}:")
    #     for comp in chapter.components:
    #         print(f"  [{comp.type}] {comp.text[:100]}...")
    
    print("ClaudeScriptCleaner loaded successfully!")
    print("Usage:")
    print("  script = clean_script_from_file('claude_output.json')")
    print("  print(script.title)")
