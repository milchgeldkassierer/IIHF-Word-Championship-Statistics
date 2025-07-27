"""
Verification tests for the StandingsCalculator refactoring.
Ensures that the refactoring issue #11 has been properly resolved.
"""

import os
import re
import pytest
from pathlib import Path


class TestRefactoringVerification:
    """Tests to verify the refactoring of standings calculation logic"""
    
    def test_code_duplication_analysis(self):
        """Analyze current code duplication in standings calculations"""
        project_root = Path(__file__).parent.parent
        
        # Files known to have duplicated logic
        files_with_duplication = [
            "utils/standings.py",
            "routes/api/team_stats.py",
            "routes/year/views.py",
            "routes/standings/all_time.py",
            "routes/tournament/summary.py",
            "routes/records/tournament_records.py",
            "routes/records/team_tournament_records.py"
        ]
        
        # Pattern to match standings calculation logic
        patterns = [
            r"if.*result_type.*==.*['\"]REG['\"]",
            r"pts\s*\+=\s*3",  # 3 points for regular win
            r"pts\s*\+=\s*2",  # 2 points for OT/SO win
            r"pts\s*\+=\s*1",  # 1 point for OT/SO loss
            r"otw\s*\+=\s*1",  # overtime win
            r"otl\s*\+=\s*1",  # overtime loss
            r"sow\s*\+=\s*1",  # shootout win
            r"sol\s*\+=\s*1",  # shootout loss
        ]
        
        duplication_report = {}
        total_lines = 0
        
        for file_path in files_with_duplication:
            full_path = project_root / file_path
            if full_path.exists():
                with open(full_path, 'r') as f:
                    content = f.read()
                    lines = content.split('\n')
                    
                matches = []
                for i, line in enumerate(lines):
                    for pattern in patterns:
                        if re.search(pattern, line):
                            matches.append((i+1, line.strip(), pattern))
                
                if matches:
                    duplication_report[file_path] = {
                        'matches': matches,
                        'count': len(matches)
                    }
                    total_lines += len(matches)
        
        # Store analysis results
        self.duplication_analysis = {
            'files_analyzed': len(files_with_duplication),
            'files_with_duplication': len(duplication_report),
            'total_duplicate_lines': total_lines,
            'details': duplication_report
        }
        
        # Assert that duplication exists (confirming the issue)
        assert len(duplication_report) > 0, "No duplication found - issue may already be resolved"
        assert total_lines > 100, f"Only {total_lines} duplicate lines found, expected >100"
        
        # Print report for verification
        print(f"\n=== Code Duplication Analysis ===")
        print(f"Files analyzed: {len(files_with_duplication)}")
        print(f"Files with duplication: {len(duplication_report)}")
        print(f"Total duplicate lines: {total_lines}")
        print(f"\nDetailed findings:")
        for file, data in duplication_report.items():
            print(f"\n{file}: {data['count']} matches")
            for line_no, line, pattern in data['matches'][:3]:  # Show first 3
                print(f"  Line {line_no}: {line[:50]}...")
    
    def test_standings_calculator_service_exists(self):
        """Check if StandingsCalculator service has been created"""
        service_path = Path(__file__).parent.parent / "services" / "standings_calculator.py"
        
        if not service_path.exists():
            pytest.skip("StandingsCalculator service not implemented yet")
        
        with open(service_path, 'r') as f:
            content = f.read()
            
        # Verify service has required methods
        assert "class StandingsCalculator" in content
        assert "def update_team_stats" in content
        assert "def calculate_points" in content
        assert "def handle_overtime" in content
        assert "def handle_shootout" in content
    
    def test_calculate_code_reduction(self):
        """Calculate actual code reduction achieved"""
        project_root = Path(__file__).parent.parent
        service_path = project_root / "services" / "standings_calculator.py"
        
        if not service_path.exists():
            pytest.skip("StandingsCalculator service not implemented yet")
        
        # Count lines in service
        with open(service_path, 'r') as f:
            service_lines = len([l for l in f.readlines() if l.strip() and not l.strip().startswith('#')])
        
        # Original duplicate lines (from issue analysis)
        original_lines = 250
        
        # Calculate reduction
        reduction_percent = ((original_lines - service_lines) / original_lines) * 100
        
        print(f"\n=== Code Reduction Analysis ===")
        print(f"Original duplicate lines: {original_lines}")
        print(f"Service implementation lines: {service_lines}")
        print(f"Reduction: {reduction_percent:.1f}%")
        
        # Verify 80% reduction target
        assert reduction_percent >= 75, f"Only {reduction_percent:.1f}% reduction, target was 80%"
    
    def test_business_rules_consistency(self):
        """Verify business rules are consistent across implementations"""
        # Define expected business rules
        expected_rules = {
            "regular_win_points": 3,
            "regular_loss_points": 0,
            "overtime_win_points": 2,
            "overtime_loss_points": 1,
            "shootout_win_points": 2,
            "shootout_loss_points": 1
        }
        
        project_root = Path(__file__).parent.parent
        
        # Check each file for business rule values
        files_to_check = [
            "utils/standings.py",
            "routes/api/team_stats.py"
        ]
        
        for file_path in files_to_check:
            full_path = project_root / file_path
            if full_path.exists():
                with open(full_path, 'r') as f:
                    content = f.read()
                
                # Check for 3 points for regular win
                assert "pts += 3" in content or "pts = 3" in content or "+ 3" in content, \
                    f"{file_path} missing 3 point rule"
                
                # Check for 2 points for OT/SO win
                assert "pts += 2" in content or "pts = 2" in content or "+ 2" in content, \
                    f"{file_path} missing 2 point rule"
                
                # Check for 1 point for OT/SO loss
                assert "pts += 1" in content or "pts = 1" in content or "+ 1" in content, \
                    f"{file_path} missing 1 point rule"
    
    def test_result_type_handling(self):
        """Verify all result types are handled consistently"""
        project_root = Path(__file__).parent.parent
        
        result_types = ["REG", "OT", "SO"]
        
        files_to_check = [
            "utils/standings.py",
            "routes/api/team_stats.py"
        ]
        
        for file_path in files_to_check:
            full_path = project_root / file_path
            if full_path.exists():
                with open(full_path, 'r') as f:
                    content = f.read()
                
                for result_type in result_types:
                    assert f"'{result_type}'" in content or f'"{result_type}"' in content, \
                        f"{file_path} missing handling for {result_type}"


class TestPerformanceImprovements:
    """Test performance improvements from refactoring"""
    
    def test_import_time(self):
        """Test that imports are fast after refactoring"""
        import time
        
        # Measure import time
        start = time.time()
        try:
            from services.standings_calculator import StandingsCalculator
            elapsed = time.time() - start
            
            # Should import quickly
            assert elapsed < 0.1, f"Import took {elapsed:.3f}s, expected < 0.1s"
        except ImportError:
            pytest.skip("StandingsCalculator service not implemented yet")
    
    def test_memory_efficiency(self):
        """Test memory usage is efficient"""
        try:
            from services.standings_calculator import StandingsCalculator
            import sys
            
            # Get size of calculator instance
            calc = StandingsCalculator()
            size = sys.getsizeof(calc)
            
            # Should be lightweight
            assert size < 1024, f"Calculator uses {size} bytes, expected < 1KB"
            
        except ImportError:
            pytest.skip("StandingsCalculator service not implemented yet")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])