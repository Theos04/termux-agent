#!/bin/bash
# ~/.bashrc or ~/.zshrc additions

# ============================================
# CORE NAVIGATION & SEARCH
# ============================================

# Interactive file browser with preview
alias fzf-preview='fzf --preview "bat --style=numbers --color=always {}"'

# Enhanced tree + preview
ft() {
    fd . | fzf \
        --preview 'eza --tree --icons --level=2 $(dirname {}) && echo && bat --color=always {}' \
        --bind 'enter:execute(code --goto {})'
}

# Search code with preview
fs() {
    rg "$1" | fzf \
        --delimiter : \
        --preview 'bat --highlight-line {2} {1}' \
        --bind 'enter:execute(code --goto {1}:{2})'
}

# Search and open in editor
fedit() {
    rg "$1" | fzf \
        --delimiter : \
        --preview 'bat --highlight-line {2} {1}' \
        --bind 'enter:execute(code --goto {1}:{2})'
}

# ============================================
# PYTHON CODE NAVIGATION
# ============================================

# Browse Python functions
fdef() {
    rg "^def " "$1" | fzf \
        --delimiter : \
        --preview 'bat {1} --highlight-line {2}' \
        --bind 'enter:execute(code --goto {1}:{2})'
}

# Browse Python classes
fclass() {
    rg "^class " "$1" | fzf \
        --delimiter : \
        --preview 'bat {1} --highlight-line {2}' \
        --bind 'enter:execute(code --goto {1}:{2})'
}

# Full code outline with tree
foutline() {
    local file="${1:-$(fzf --preview 'bat --color=always {}')}"
    awk '
    /^class / {
        print "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        print "📦 " $2
        print "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        next
    }
    /^def / {
        print "  🔹 " $2
        next
    }
    /^    def / {
        print "    ├── " $2
        next
    }
    /^    async def / {
        print "    ├── ⚡ " $2
        next
    }
    /^    @/ && /\./ {
        print "      📍 Decorator: " $0
        next
    }
    ' "$file" | less -R
}

# Compact class summary
fsummary() {
    local file="${1:-$(fzf --preview 'bat --color=always {}')}"
    awk '
    /^class /{
        if(cls!=""){
            print cls " (" n " methods)"
        }
        cls=$2
        n=0
        next
    }
    /^    def /{
        n++
    }
    END{
        print cls " (" n " methods)"
    }
    ' "$file"
}

# ============================================
# CODE ANALYSIS
# ============================================

# Find all TODO/FIXME/BUG
ftodo() {
    rg "TODO|FIXME|BUG|HACK" . \
        | fzf --delimiter : \
        --preview 'bat --highlight-line {2} {1}' \
        --bind 'enter:execute(code --goto {1}:{2})'
}

# Find imports
fimports() {
    rg "^import |^from " | fzf \
        --delimiter : \
        --preview 'bat --highlight-line {2} {1}' \
        --bind 'enter:execute(code --goto {1}:{2})'
}

# Find function calls
fcalls() {
    rg "\b$1\(" . | fzf \
        --delimiter : \
        --preview 'bat --highlight-line {2} {1}' \
        --bind 'enter:execute(code --goto {1}:{2})'
}

# ============================================
# GIT INTEGRATION
# ============================================

# Git changed files with diff preview
fgdiff() {
    git diff --name-only | fzf \
        --preview 'git diff --color=always {}' \
        --bind 'enter:execute(code --goto {})'
}

# Git log browser
fglog() {
    git log --oneline | fzf \
        --preview 'git show --color=always {1}' \
        --bind 'enter:execute(git show {1} | less -R)'
}

# Git branches with graph
fgbranch() {
    git branch | fzf \
        --preview 'git log --graph --oneline --decorate --color=always {}' \
        --bind 'enter:execute(git checkout {1})'
}

# ============================================
# FILE MANAGEMENT
# ============================================

# Recent files
frecent() {
    find . -type f -printf "%T@ %p\n" \
        | sort -nr \
        | head -200 \
        | cut -d' ' -f2- \
        | fzf --preview 'bat --color=always {}'
}

# Largest files
flarge() {
    find . -type f -exec du -h {} + \
        | sort -hr \
        | head -50 \
        | fzf --preview 'bat --color=always {2}'
}

# Largest directories
fdirs() {
    du -sh * | sort -hr | fzf --preview 'eza --tree --icons {}'
}

# ============================================
# PROCESS MANAGEMENT
# ============================================

# Kill process interactively
fkill() {
    ps -ef | fzf \
        --preview 'ps aux | grep {2}' \
        --bind 'enter:execute(kill -9 {2})'
}

# Docker containers
fdocker() {
    docker ps | fzf \
        --preview 'docker logs --tail 50 {1}' \
        --bind 'enter:execute(docker exec -it {1} /bin/bash)'
}

# ============================================
# DATA VIEWERS
# ============================================

# JSON viewer
fjson() {
    fzf --preview 'jq . {}'
}

# CSV viewer
fcsv() {
    fzf --preview 'column -s, -t < {} | less -S'
}

# Markdown viewer
fmd() {
    fzf --preview 'glow {}'
}

# ============================================
# PROJECT DASHBOARD
# ============================================

# Live project dashboard
fdashboard() {
    watch -n2 '
    clear
    echo "╔══════════════════════════════════════════════════╗"
    echo "║            📊 PROJECT DASHBOARD                 ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo ""
    echo "📁 FILES:"
    echo "  Total: $(find . -type f | wc -l)"
    echo "  Python: $(fd -e py | wc -l)"
    echo "  YAML/JSON: $(fd -e yml -e yaml -e json | wc -l)"
    echo ""
    echo "📦 DEPENDENCIES:"
    if [ -f requirements.txt ]; then
        echo "  $(wc -l < requirements.txt) packages"
    elif [ -f pyproject.toml ]; then
        grep -E "^[a-zA-Z]" pyproject.toml | head -5
    fi
    echo ""
    echo "🔍 TODOs:"
    rg "TODO|FIXME" . | wc -l | xargs echo "  Count:"
    rg "TODO|FIXME" . | head -3
    echo ""
    echo "📈 GIT:"
    git status --short | wc -l | xargs echo "  Changed files:"
    echo "  Branch: $(git branch --show-current)"
    echo ""
    echo "💾 MEMORY:"
    free -h | grep -E "Mem|Swap" | sed "s/^/  /"
    '
}

# ============================================
# CODE MAP GENERATORS
# ============================================

# Generate interactive code map
fmap() {
    local file="${1:-$(fzf --preview 'bat --color=always {}')}"
    echo "Generating code map for $file..."
    echo ""
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📌 CLASSES & METHODS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    awk '
    /^class / {
        print "\n📦 " $2
        next
    }
    /^    def / {
        print "  ├── " $2
        next
    }
    /^    async def / {
        print "  ├── ⚡ " $2
        next
    }
    /^    @property/ {
        print "  ├── 🏷️  " $2
        next
    }
    /^    @classmethod/ {
        print "  ├── 🔄 " $2
        next
    }
    /^    @staticmethod/ {
        print "  ├── ⚙️  " $2
        next
    }
    ' "$file"
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📌 TOP-LEVEL FUNCTIONS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    awk '
    /^def / && !/^    def/ {
        print "🔹 " $2
        next
    }
    /^async def / && !/^    async def/ {
        print "⚡ " $2
        next
    }
    ' "$file"
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📌 IMPORTS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    grep -E "^import |^from " "$file" | sed 's/^/  • /'
}

# Generate call graph
fcallgraph() {
    local file="${1:-$(fzf --preview 'bat --color=always {}')}"
    echo "Generating call graph for $file..."
    
    # Extract function calls
    awk '
    /^def / {
        func = $2
        gsub(/\(.*/, "", func)
        print "FUNCTION: " func
        next
    }
    /^[[:space:]]+[a-zA-Z_][a-zA-Z0-9_]*\(/ {
        call = $0
        gsub(/^[[:space:]]+/, "", call)
        gsub(/\(.*/, "", call)
        if (call !~ /^(if|for|while|return|print|assert|raise)$/) {
            print "  └─ calls: " call
        }
    }
    ' "$file"
}

# ============================================
# DEBUGGING TOOLS
# ============================================

# Python traceback finder
ftrace() {
    rg "Traceback|Exception|Error|raise" . | fzf \
        --delimiter : \
        --preview 'bat --highlight-line {2} {1}' \
        --bind 'enter:execute(code --goto {1}:{2})'
}

# Memory profiler view
fmem() {
    echo "Memory Usage:"
    ps aux --sort=-%mem | head -10 | awk '{print $2, $4, $11}'
    echo ""
    echo "Press Enter to refresh..."
    read
}

# CPU profiler view
fcpu() {
    echo "CPU Usage:"
    ps aux --sort=-%cpu | head -10 | awk '{print $2, $3, $11}'
    echo ""
    echo "Press Enter to refresh..."
    read
}

# ============================================
# ADVANCED PYTHON TOOLS
# ============================================

# Python dependency analyzer
fpydeptree() {
    if [ -f requirements.txt ]; then
        echo "📦 Dependency Tree:"
        pipdeptree | fzf --preview 'pip show {1}' \
            --bind 'enter:execute(pip show {1} | less)'
    else
        echo "No requirements.txt found"
    fi
}

# Find unused imports
fpyunused() {
    echo "🔍 Finding unused imports..."
    if command -v autoflake &> /dev/null; then
        autoflake -r --check . | fzf --preview 'bat {1}'
    else
        echo "Install autoflake: pip install autoflake"
    fi
}

# Python style checker
fpystyle() {
    local file="${1:-$(fzf --preview 'bat --color=always {}')}"
    if command -v flake8 &> /dev/null; then
        flake8 "$file" | fzf --preview 'bat {1}'
    else
        echo "Install flake8: pip install flake8"
    fi
}

# ============================================
# TMUX INTEGRATION
# ============================================

# Start development session
fdev() {
    tmux new-session -d -s dev
    tmux split-window -h
    tmux split-window -v
    tmux select-pane -t 0
    tmux send-keys 'fdashboard' C-m
    tmux select-pane -t 1
    tmux send-keys 'btop' C-m
    tmux select-pane -t 2
    tmux send-keys 'lazygit' C-m
    tmux attach-session -t dev
}

# Quick debug session
fdebug() {
    tmux new-session -d -s debug
    tmux split-window -v
    tmux split-window -h
    tmux select-pane -t 0
    tmux send-keys 'ipython' C-m
    tmux select-pane -t 1
    tmux send-keys 'watch -n2 "ps aux | grep python"' C-m
    tmux select-pane -t 2
    tmux send-keys 'tail -f logs/*.log | rg --line-buffered ERROR' C-m
    tmux attach-session -t debug
}

# ============================================
# KEY BINDINGS (fzf)
# ============================================

# Enable fzf key bindings
[ -f ~/.fzf.zsh ] && source ~/.fzf.zsh
[ -f ~/.fzf.bash ] && source ~/.fzf.bash

# Custom key bindings
bind '"\C-g": "fzf-preview\n"'           # Ctrl+G = file browser
bind '"\C-s": "fs\n"'                    # Ctrl+S = search
bind '"\C-f": "fdef\n"'                  # Ctrl+F = find functions
bind '"\C-c": "fclass\n"'                # Ctrl+C = find classes
bind '"\C-t": "ftodo\n"'                 # Ctrl+T = find todos

# ============================================
# INSTALLATION CHECK
# ============================================

echo "✅ Toolkit loaded!"
echo ""
echo "📋 Available Commands:"
echo "  ft         - File tree browser"
echo "  fs         - Search code with preview"
echo "  fedit      - Search and edit files"
echo "  fdef       - Browse Python functions"
echo "  fclass     - Browse Python classes"
echo "  foutline   - Full code outline with tree"
echo "  fsummary   - Class method summary"
echo "  ftodo      - Find all TODOs/FIXMEs"
echo "  fimports   - Browse imports"
echo "  fcalls     - Find function calls"
echo "  fgdiff     - Git diff browser"
echo "  fglog      - Git log browser"
echo "  fgbranch   - Git branch browser"
echo "  frecent    - Recent files"
echo "  flarge     - Largest files"
echo "  fdirs      - Largest directories"
echo "  fkill      - Kill process interactively"
echo "  fdocker    - Docker container browser"
echo "  fjson      - JSON viewer"
echo "  fcsv       - CSV viewer"
echo "  fmd        - Markdown viewer"
echo "  fdashboard - Live project dashboard"
echo "  fmap       - Generate code map"
echo "  fcallgraph - Function call graph"
echo "  ftrace     - Python traceback finder"
echo "  fdev       - Start development tmux session"
echo "  fdebug     - Start debugging tmux session"
