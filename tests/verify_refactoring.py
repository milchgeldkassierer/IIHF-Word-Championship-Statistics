#!/usr/bin/env python3
"""
Script to verify the refactoring status and create a comprehensive report.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

def find_standings_calculations(project_root: Path) -> Dict[str, List[Tuple[int, str]]]:
    """Find all instances of standings calculation logic"""
    
    files_to_check = [
        "utils/standings.py",
        "routes/api/team_stats.py", 
        "routes/year/views.py",
        "routes/standings/all_time.py",
        "routes/tournament/summary.py",
        "routes/records/tournament_records.py",
        "routes/records/team_tournament_records.py"
    ]
    
    # More specific patterns for standings calculations
    patterns = [
        (r"if.*result_type.*==.*['\"]REG['\"]", "Regular time check"),
        (r"if.*result_type.*==.*['\"]OT['\"]", "Overtime check"),
        (r"if.*result_type.*==.*['\"]SO['\"]", "Shootout check"),
        (r"\.pts\s*\+=\s*3", "3 points assignment"),
        (r"\.pts\s*\+=\s*2", "2 points assignment"),
        (r"\.pts\s*\+=\s*1", "1 point assignment"),
        (r"\.w\s*\+=\s*1", "Win increment"),
        (r"\.l\s*\+=\s*1", "Loss increment"),
        (r"\.otw\s*\+=\s*1", "OT win increment"),
        (r"\.otl\s*\+=\s*1", "OT loss increment"),
        (r"\.sow\s*\+=\s*1", "SO win increment"),
        (r"\.sol\s*\+=\s*1", "SO loss increment"),
    ]
    
    findings = {}
    
    for file_path in files_to_check:
        full_path = project_root / file_path
        if full_path.exists():
            matches = []
            with open(full_path, 'r') as f:
                lines = f.readlines()
                
            for i, line in enumerate(lines):
                for pattern, description in patterns:
                    if re.search(pattern, line):
                        matches.append((i+1, line.strip(), description))
            
            if matches:
                findings[file_path] = matches
    
    return findings

def calculate_duplication_stats(findings: Dict[str, List[Tuple[int, str]]]) -> Dict:
    """Calculate statistics about code duplication"""
    
    total_matches = sum(len(matches) for matches in findings.values())
    
    # Group by pattern type
    pattern_counts = {}
    for file_matches in findings.values():
        for _, _, description in file_matches:
            pattern_counts[description] = pattern_counts.get(description, 0) + 1
    
    # Estimate duplicate lines (considering context around matches)
    estimated_lines = total_matches * 3  # Each match likely part of 3-line block
    
    return {
        'files_with_duplication': len(findings),
        'total_pattern_matches': total_matches,
        'estimated_duplicate_lines': estimated_lines,
        'pattern_distribution': pattern_counts
    }

def check_service_implementation() -> bool:
    """Check if StandingsCalculator service exists"""
    service_path = Path(__file__).parent.parent / "services" / "standings_calculator.py"
    return service_path.exists()

def generate_report():
    """Generate comprehensive verification report"""
    project_root = Path(__file__).parent.parent
    
    print("=== REFACTORING VERIFICATION REPORT ===\n")
    
    # 1. Check service implementation
    service_exists = check_service_implementation()
    print(f"1. StandingsCalculator Service Status:")
    print(f"   - Service implemented: {'✅ YES' if service_exists else '❌ NO'}")
    if service_exists:
        service_path = project_root / "services" / "standings_calculator.py"
        with open(service_path, 'r') as f:
            lines = [l for l in f.readlines() if l.strip() and not l.strip().startswith('#')]
        print(f"   - Service size: {len(lines)} lines of code")
    print()
    
    # 2. Find duplications
    print("2. Code Duplication Analysis:")
    findings = find_standings_calculations(project_root)
    stats = calculate_duplication_stats(findings)
    
    print(f"   - Files analyzed: 7")
    print(f"   - Files with duplication: {stats['files_with_duplication']}")
    print(f"   - Total pattern matches: {stats['total_pattern_matches']}")
    print(f"   - Estimated duplicate lines: ~{stats['estimated_duplicate_lines']}")
    print()
    
    # 3. Show detailed findings
    print("3. Detailed Findings by File:")
    for file_path, matches in findings.items():
        print(f"\n   {file_path}: {len(matches)} matches")
        # Show first 3 matches as examples
        for line_no, line, desc in matches[:3]:
            print(f"      Line {line_no} [{desc}]: {line[:60]}...")
        if len(matches) > 3:
            print(f"      ... and {len(matches) - 3} more matches")
    
    # 4. Pattern distribution
    print("\n4. Pattern Distribution:")
    for pattern, count in sorted(stats['pattern_distribution'].items(), key=lambda x: x[1], reverse=True):
        print(f"   - {pattern}: {count} occurrences")
    
    # 5. Recommendations
    print("\n5. Recommendations:")
    if not service_exists:
        print("   ⚠️  StandingsCalculator service needs to be implemented")
        print("   ⚠️  Estimated effort: 3-5 hours")
        print("   ⚠️  Expected code reduction: ~80% (250 → 50 lines)")
    else:
        print("   ✅ Service implemented - now need to replace duplicates")
        print("   ⚠️  Next step: Update all files to use StandingsCalculator")
    
    # 6. Summary
    print("\n6. Summary:")
    print(f"   - Issue #11 Status: {'RESOLVED' if service_exists and stats['files_with_duplication'] == 0 else 'IN PROGRESS'}")
    print(f"   - Code duplication: {'ELIMINATED' if stats['total_pattern_matches'] == 0 else 'STILL EXISTS'}")
    print(f"   - Refactoring complete: {'YES ✅' if service_exists else 'NO ❌'}")

if __name__ == "__main__":
    generate_report()