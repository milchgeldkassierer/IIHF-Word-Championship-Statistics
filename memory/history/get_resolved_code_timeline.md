# Evolution Timeline: get_resolved_code Function Duplication

## Summary
The `get_resolved_code` function was introduced by Andre Kurth on May 22, 2025, and has been duplicated across 5 different files through copy-paste during various refactoring efforts. The developer was aware of the duplication (as evidenced by comments) but continued the pattern, likely due to time pressure or circular import concerns.

## Timeline

### Phase 1: Original Introduction (May 22, 2025)
- **Commit**: `f61fa60` 
- **Author**: Andre Kurth
- **Location**: `app.py`
- **Context**: Part of "Add team stats tables and enhance sorting logic"
- **Purpose**: Resolve playoff placeholder codes (W(QF1), L(SF2)) to actual team codes

### Phase 2: First Duplication (May 26, 2025)
- **Commit**: `ba34493`
- **Event**: Function copied to `routes/year_routes.py`
- **Comment found**: `# Definition of get_resolved_code (copied and adapted from year_view)`
- **Significance**: Developer explicitly acknowledged copying

### Phase 3: Spreading to New Features (June-July 2025)
- **June 16**: Copied to `routes/record_routes.py` for records functionality
- **July 10**: Added to `routes/main_routes.py` for all-time standings
- **Pattern**: Each new feature that needed playoff resolution got its own copy

### Phase 4: Modularization Refactoring (July 10-11, 2025)
- **July 10**: `year_routes.py` split into modules:
  - `routes/year/views.py` 
  - `routes/year/games.py` (with comment: "Use the same get_resolved_code function as year_view")
  - `routes/year/seeding.py`
- **July 10**: `record_routes.py` split, function moved to `routes/records/utils.py`
- **July 11**: Added to `routes/api/team_stats.py`

## Current State (as of July 26, 2025)

### Files containing `get_resolved_code`:
1. `routes/year/views.py` - Line 181
2. `routes/year/games.py` - With acknowledgment comment
3. `routes/year/seeding.py` - Line 295
4. `routes/records/utils.py` - From record_routes refactoring
5. `routes/api/team_stats.py` - Latest addition

### Technical Debt Impact:
- **Maintenance Risk**: HIGH - Bug fixes must be applied in 5 locations
- **Consistency Risk**: MEDIUM - Slight formatting differences already exist
- **Testing Burden**: HIGH - Same logic tested multiple times
- **Code Smell**: Strong - Violates DRY principle

### Root Causes:
1. **Rapid Development**: Multiple features added quickly
2. **Import Challenges**: Likely circular import issues
3. **Refactoring Pattern**: "Split now, consolidate later" approach
4. **Developer Awareness**: Comments show awareness but no immediate action

## Recommendations:
1. Create `utils/playoff_resolver.py` module
2. Move function to shared location
3. Update all 5 locations to import from shared module
4. Add comprehensive tests for the single implementation
5. Document the resolution algorithm properly