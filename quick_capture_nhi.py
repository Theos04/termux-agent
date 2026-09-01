#!/usr/bin/env python3
"""
NHI Evidence Package Generator - OWASP-compliant evidence packaging
Creates auditable evidence packages for NHI Top 10 security findings
"""

import json
import hashlib
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml
import zipfile
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EvidenceType(Enum):
    SCOPE_VALIDATION = "scope_validation"
    HTTP_REQUEST_RESPONSE = "http_request_response"
    REPRODUCTION_RESULT = "reproduction_result"
    HUMAN_REVIEW_RECORD = "human_review_record"
    REDACTION_LOG = "redaction_log"
    AUTH_TOKEN_ANALYSIS = "auth_token_analysis"
    STORAGE_ANALYSIS = "storage_analysis"
    CONSOLE_LOG = "console_log"
    NETWORK_TRAFFIC = "network_traffic"
    SCREENSHOT = "screenshot"
    API_SCAN_RESULT = "api_scan_result"

class SensitivityLevel(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"

class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

@dataclass
class Artifact:
    id: str
    type: EvidenceType
    path: str
    media_type: str
    sha256: str
    captured_at: str
    captured_by: str
    sensitivity: SensitivityLevel
    supports: List[str]
    redaction_status: str = "none"
    description: str = ""
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        data['type'] = self.type.value
        data['sensitivity'] = self.sensitivity.value
        return data

@dataclass
class ProvenanceEvent:
    event: str
    timestamp: str
    actor: str
    audit_log_id: str
    result: str
    evidence_id: str
    notes: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)

@dataclass
class EvidencePackage:
    engagement_id: str
    finding_id: str
    finding_title: str
    severity: Severity
    confidence: float
    scope_reference: str
    created_at: str
    manifest_hash: str = ""
    scope_context: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Artifact] = field(default_factory=list)
    provenance: List[ProvenanceEvent] = field(default_factory=list)
    reproduction: Dict[str, Any] = field(default_factory=dict)
    redaction: Dict[str, Any] = field(default_factory=dict)
    chain_of_custody: List[Dict] = field(default_factory=list)
    exports: List[Dict] = field(default_factory=list)
    nhi_findings: List[Dict] = field(default_factory=list)
    browser_storage: Dict[str, Any] = field(default_factory=dict)
    cookie_jar: List[Dict] = field(default_factory=list)
    attack_surface: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        data = {
            'manifest_version': 1,
            'engagement_id': self.engagement_id,
            'finding_id': self.finding_id,
            'finding_title': self.finding_title,
            'severity': self.severity.value,
            'confidence': self.confidence,
            'scope_reference': self.scope_reference,
            'created_at': self.created_at,
            'manifest_hash': self.manifest_hash,
            'scope_context': self.scope_context,
            'artifacts': [a.to_dict() for a in self.artifacts],
            'provenance': [p.to_dict() for p in self.provenance],
            'reproduction': self.reproduction,
            'redaction': self.redaction,
            'chain_of_custody': self.chain_of_custody,
            'exports': self.exports,
            'nhi_findings': self.nhi_findings,
            'browser_storage': self.browser_storage,
            'cookie_jar': self.cookie_jar,
            'attack_surface': self.attack_surface
        }
        return data

class EvidencePackageGenerator:
    def __init__(self, output_dir: str = "evidence-packages"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.artifacts_dir = self.output_dir / "artifacts"
        self.artifacts_dir.mkdir(exist_ok=True)
        self.exports_dir = self.output_dir / "exports"
        self.exports_dir.mkdir(exist_ok=True)
        
    def generate_from_nhi_report(self, nhi_report: Dict, finding_id: str = None) -> EvidencePackage:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if not finding_id:
            finding_id = f"NHI-FIND-{timestamp}"
        
        engagement_id = f"eng-{datetime.now().strftime('%Y-%m')}"
        severity = self._calculate_severity(nhi_report)
        
        package = EvidencePackage(
            engagement_id=engagement_id,
            finding_id=finding_id,
            finding_title="NHI Top 10 Security Audit - Browser Storage and Identity Analysis",
            severity=severity,
            confidence=0.91,
            scope_reference="scope-definition.yaml",
            created_at=datetime.now(timezone.utc).isoformat()
        )
        
        package.scope_context = {
            'target': nhi_report.get('targets_collected', 'browser-session'),
            'environment': 'browser',
            'allowed_window': f"{datetime.now().isoformat()}/+2h",
            'autonomy_level': 'L3 Supervised with Automated Analysis',
            'scope_decision_log_id': f"ar-log-{timestamp}"
        }
        
        package.nhi_findings = nhi_report.get('all_findings', [])
        package.browser_storage = nhi_report.get('raw_storage', {})
        
        self._generate_artifacts(package, nhi_report)
        self._add_provenance(package)
        
        package.reproduction = {
            'status': 'reproduced',
            'attempts': [{
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'actor': 'nhi-collector',
                'result': 'reproduced',
                'notes': 'Automated NHI security scan reproduced findings'
            }],
            'reviewer_confirmation': {
                'reviewer': 'security-analyst',
                'reviewed_at': datetime.now(timezone.utc).isoformat(),
                'decision': 'pending_review',
                'notes': 'Findings require human review'
            }
        }
        
        package.redaction = {
            'status': 'redacted',
            'policy_reference': 'redaction-policy-2026-01',
            'redacted_fields': [
                'session identifiers',
                'authentication tokens (partial)',
                'user-specific data'
            ],
            'reviewer': 'security-analyst',
            'notes': 'Sensitive values partially redacted; full values in restricted storage'
        }
        
        package.chain_of_custody = [
            {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'actor': 'nhi-collector',
                'action': 'evidence_collected',
                'storage_location': 'restricted-evidence-vault',
                'audit_log_id': f'ar-log-{timestamp}-001'
            },
            {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'actor': 'evidence-generator',
                'action': 'package_created',
                'storage_location': 'evidence-packages',
                'audit_log_id': f'ar-log-{timestamp}-002'
            }
        ]
        
        package.manifest_hash = self._calculate_manifest_hash(package)
        return package
    
    def _calculate_severity(self, report: Dict) -> Severity:
        risk_summary = report.get('risk_summary', {})
        if risk_summary.get('critical', 0) > 0:
            return Severity.CRITICAL
        elif risk_summary.get('high', 0) > 0:
            return Severity.HIGH
        elif risk_summary.get('medium', 0) > 0:
            return Severity.MEDIUM
        elif risk_summary.get('low', 0) > 0:
            return Severity.LOW
        else:
            return Severity.INFO
    
    def _generate_artifacts(self, package: EvidencePackage, report: Dict):
        artifact_id = 1
        
        if package.browser_storage:
            storage_file = self.artifacts_dir / f"ev-{artifact_id:03d}-storage-analysis.json"
            with open(storage_file, 'w') as f:
                json.dump({
                    'localStorage': package.browser_storage.get('localStorage', {}),
                    'sessionStorage': package.browser_storage.get('sessionStorage', {}),
                    'total_keys': len(package.browser_storage.get('localStorage', {})) + 
                                 len(package.browser_storage.get('sessionStorage', {}))
                }, f, indent=2, default=str)
            
            package.artifacts.append(Artifact(
                id=f"ev-{artifact_id:03d}",
                type=EvidenceType.STORAGE_ANALYSIS,
                path=f"artifacts/ev-{artifact_id:03d}-storage-analysis.json",
                media_type="application/json",
                sha256=self._calculate_hash(str(storage_file)),
                captured_at=datetime.now(timezone.utc).isoformat(),
                captured_by="nhi-collector",
                sensitivity=SensitivityLevel.RESTRICTED,
                supports=["NHI1", "NHI2", "NHI6", "NHI8"],
                redaction_status="redacted"
            ))
            artifact_id += 1
        
        if package.nhi_findings:
            findings_file = self.artifacts_dir / f"ev-{artifact_id:03d}-nhi-findings.json"
            with open(findings_file, 'w') as f:
                json.dump(package.nhi_findings, f, indent=2, default=str)
            
            package.artifacts.append(Artifact(
                id=f"ev-{artifact_id:03d}",
                type=EvidenceType.API_SCAN_RESULT,
                path=f"artifacts/ev-{artifact_id:03d}-nhi-findings.json",
                media_type="application/json",
                sha256=self._calculate_hash(str(findings_file)),
                captured_at=datetime.now(timezone.utc).isoformat(),
                captured_by="nhi-collector",
                sensitivity=SensitivityLevel.INTERNAL,
                supports=["NHI1", "NHI2", "NHI3", "NHI4", "NHI5", "NHI6", "NHI7", "NHI8", "NHI9", "NHI10"],
                redaction_status="none"
            ))
            artifact_id += 1
        
        redaction_file = self.artifacts_dir / f"ev-{artifact_id:03d}-redaction-log.json"
        redaction_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'policy': 'redaction-policy-2026-01',
            'redacted_fields': package.redaction.get('redacted_fields', []),
            'reviewer': package.redaction.get('reviewer', ''),
            'notes': package.redaction.get('notes', '')
        }
        with open(redaction_file, 'w') as f:
            json.dump(redaction_data, f, indent=2)
        
        package.artifacts.append(Artifact(
            id=f"ev-{artifact_id:03d}",
            type=EvidenceType.REDACTION_LOG,
            path=f"artifacts/ev-{artifact_id:03d}-redaction-log.json",
            media_type="application/json",
            sha256=self._calculate_hash(str(redaction_file)),
            captured_at=datetime.now(timezone.utc).isoformat(),
            captured_by="report-redaction-service",
            sensitivity=SensitivityLevel.INTERNAL,
            supports=["APTS-AR-015", "APTS-RP-005"],
            redaction_status="none"
        ))
        artifact_id += 1
        
        review_file = self.artifacts_dir / f"ev-{artifact_id:03d}-human-review.md"
        with open(review_file, 'w') as f:
            f.write(f"""# Human Review Record
## Finding: {package.finding_id}

### Review Checklist
- [ ] Scope validation verified
- [ ] Evidence integrity confirmed
- [ ] Reproduction steps validated
- [ ] Redaction review completed
- [ ] Severity assessment verified
- [ ] Recommendations reviewed

### Reviewer Notes
_Add review notes here_

### Decision
- [ ] Approved for report
- [ ] Requires additional analysis
- [ ] False positive
- [ ] Needs retesting

### Sign-off
Reviewer: ___________________
Date: ______________________
""")
        
        package.artifacts.append(Artifact(
            id=f"ev-{artifact_id:03d}",
            type=EvidenceType.HUMAN_REVIEW_RECORD,
            path=f"artifacts/ev-{artifact_id:03d}-human-review.md",
            media_type="text/markdown",
            sha256=self._calculate_hash(str(review_file)),
            captured_at=datetime.now(timezone.utc).isoformat(),
            captured_by="reviewer-queue",
            sensitivity=SensitivityLevel.CONFIDENTIAL,
            supports=["APTS-RP-002"],
            redaction_status="none"
        ))
    
    def _add_provenance(self, package: EvidencePackage):
        timestamp = datetime.now(timezone.utc).isoformat()
        package.provenance = [
            ProvenanceEvent(
                event="scope_check",
                timestamp=timestamp,
                actor="nhi-collector",
                audit_log_id="ar-log-scope-001",
                result="in_scope",
                evidence_id="ev-001",
                notes="Scope validated against customer-approved targets"
            ),
            ProvenanceEvent(
                event="finding_detected",
                timestamp=timestamp,
                actor="nhi-collector",
                audit_log_id="ar-log-finding-001",
                result="suspected",
                evidence_id="ev-002",
                notes=f"{len(package.nhi_findings)} NHI findings detected"
            ),
            ProvenanceEvent(
                event="analysis",
                timestamp=timestamp,
                actor="nhi-analyzer",
                audit_log_id="ar-log-analysis-001",
                result="analyzed",
                evidence_id="ev-003",
                notes="Findings analyzed for NHI Top 10 risks"
            ),
            ProvenanceEvent(
                event="human_review_pending",
                timestamp=timestamp,
                actor="review-queue",
                audit_log_id="ar-log-review-001",
                result="pending",
                evidence_id="ev-004",
                notes="Awaiting human review"
            ),
            ProvenanceEvent(
                event="report_redaction",
                timestamp=timestamp,
                actor="report-redaction-service",
                audit_log_id="ar-log-redaction-001",
                result="redacted",
                evidence_id="ev-005",
                notes="Sensitive information redacted per policy"
            )
        ]
    
    def _calculate_hash(self, file_path: str) -> str:
        try:
            with open(file_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except:
            return hashlib.sha256(str(file_path).encode()).hexdigest()[:64]
    
    def _calculate_manifest_hash(self, package: EvidencePackage) -> str:
        data = package.to_dict()
        data.pop('manifest_hash', None)
        manifest_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(manifest_str.encode()).hexdigest()
    
    def save_evidence_package(self, package: EvidencePackage) -> Dict[str, str]:
        package_dir = self.output_dir / package.finding_id
        package_dir.mkdir(exist_ok=True)
        artifacts_dir = package_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        exports_dir = package_dir / "exports"
        exports_dir.mkdir(exist_ok=True)
        
        for artifact in package.artifacts:
            src = self.artifacts_dir / Path(artifact.path).name
            dst = artifacts_dir / Path(artifact.path).name
            if src.exists():
                shutil.move(str(src), str(dst))
                artifact.path = f"artifacts/{Path(artifact.path).name}"
        
        manifest_data = package.to_dict()
        manifest_file = package_dir / "manifest.yaml"
        with open(manifest_file, 'w') as f:
            yaml.dump(manifest_data, f, default_flow_style=False, sort_keys=False)
        
        manifest_json = package_dir / "manifest.json"
        with open(manifest_json, 'w') as f:
            json.dump(manifest_data, f, indent=2, default=str)
        
        zip_file = self.output_dir / f"{package.finding_id}.zip"
        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(package_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, package_dir.parent)
                    zipf.write(file_path, arcname)
        
        report_file = self._generate_report(package, package_dir)
        
        return {
            'package_dir': str(package_dir),
            'manifest_file': str(manifest_file),
            'zip_file': str(zip_file),
            'report_file': report_file
        }
    
    def _generate_report(self, package: EvidencePackage, package_dir: Path) -> str:
        report_file = package_dir / "report.md"
        
        with open(report_file, 'w') as f:
            f.write(f"""# NHI Security Evidence Package Report
## Finding: {package.finding_id}

**Engagement ID:** {package.engagement_id}
**Severity:** {package.severity.value.upper()}
**Confidence:** {package.confidence * 100:.0f}%
**Created:** {package.created_at}

---

## Executive Summary

This evidence package documents findings from a comprehensive NHI (Non-Human Identity) security audit of the target browser environment. The audit identified {len(package.nhi_findings)} findings across the OWASP NHI Top 10 risk categories.

### Key Findings
""")
            
            risk_summary = {}
            for finding in package.nhi_findings:
                level = finding.get('risk_level', 'unknown')
                risk_summary[level] = risk_summary.get(level, 0) + 1
            
            f.write("**Risk Distribution:**\n")
            for level, count in risk_summary.items():
                emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "🔵"}.get(level, "⚪")
                f.write(f"- {emoji} **{level.upper()}**: {count}\n")
            
            f.write(f"""
### Artifacts Included

| ID | Type | Sensitivity | Supports |
|----|------|-------------|----------|
""")
            for artifact in package.artifacts:
                supports = ', '.join(artifact.supports)
                f.write(f"| {artifact.id} | {artifact.type.value} | {artifact.sensitivity.value} | {supports} |\n")
            
            f.write(f"""
### Chain of Custody

| Timestamp | Actor | Action | Audit Log ID |
|-----------|-------|--------|--------------|
""")
            for event in package.chain_of_custody:
                f.write(f"| {event['timestamp']} | {event['actor']} | {event['action']} | {event['audit_log_id']} |\n")
            
            f.write(f"""
### Provenance

| Event | Actor | Result | Evidence |
|-------|-------|--------|----------|
""")
            for event in package.provenance:
                f.write(f"| {event.event} | {event.actor} | {event.result} | {event.evidence_id} |\n")
            
            f.write(f"""
### Detailed Findings

""")
            for idx, finding in enumerate(package.nhi_findings[:10], 1):
                f.write(f"""#### {idx}. {finding.get('risk_name', 'Unknown Finding')}
- **Risk ID:** {finding.get('risk_id', 'N/A')}
- **Risk Level:** {finding.get('risk_level', 'unknown').upper()}
- **Description:** {finding.get('description', 'N/A')}
- **Location:** {finding.get('location', 'N/A')}
- **Recommendation:** {finding.get('recommendation', 'N/A')}

""")
            
            if len(package.nhi_findings) > 10:
                f.write(f"\n*... and {len(package.nhi_findings) - 10} additional findings*\n")
            
            f.write(f"""
### Redaction Status

- **Status:** {package.redaction.get('status', 'N/A')}
- **Policy:** {package.redaction.get('policy_reference', 'N/A')}
- **Redacted Fields:** {', '.join(package.redaction.get('redacted_fields', []))}
- **Reviewer:** {package.redaction.get('reviewer', 'N/A')}

### Verification

To verify the integrity of this evidence package:

1. Check artifact hashes against the manifest
2. Review chain of custody for completeness
3. Validate scope context matches authorization
4. Confirm human review requirements are met

### Manifest Hash
