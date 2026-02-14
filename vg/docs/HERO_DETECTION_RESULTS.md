# Hero Detection System - Final Results

## Executive Summary

This document summarizes the results of attempting to build a hero detection system
for Vainglory replay files (.vgr format).

**Bottom Line:** Hero detection from binary replay data is **extremely challenging**.
After testing multiple approaches, we achieved only **4.67% accuracy** overall,
with one notable exception: **Grumpjaw can be detected with 100% accuracy**.

---

## Approaches Tested

### 1. Binary Pattern Matching (Hero ID)
- **Method:** Search for hero ID bytes in binary data
- **Result:** **0% accuracy**
- **Reason:** Hero IDs are not stored in a simple retrievable format

### 2. Event Ratio-Based Detection
- **Method:** Use 6 candidate event codes (0x44, 0x43, 0x0E, 0x65, 0x13, 0x76)
  and match against hero profiles using cosine similarity
- **Initial Result:** 17.76% accuracy
- **LOOCV Result:** **4.17% accuracy** (overfitting detected)
- **Reason:** All heroes have similar event ratios; not discriminative enough

### 3. Signature Event-Based Detection
- **Method:** Find hero-specific "signature events" - event codes that appear
  predominantly for specific heroes
- **LOOCV Result:** **4.67% accuracy overall**
- **Key Finding:** **Grumpjaw: 100% accuracy (5/5)**

---

## Key Technical Findings

### Event Code Analysis
- **250 unique event codes** found across 11 tournament replays
- Only a few event codes are hero-discriminative:

| Event Code | Top Hero | Concentration | Notes |
|------------|----------|---------------|-------|
| 0x08 | Grumpjaw | 65.38% | 24x average - **HIGHLY DISCRIMINATIVE** |
| 0xEE | Skaarf | 83.60% | 22x average |
| 0xEF | Skaarf | 81.37% | 19x average |
| 0xB8 | Skaarf | 79.31% | 23x average |
| 0xCE | Ylva | 66.57% | 18x average |
| 0x96 | Kensei | 67.77% | 16x average |
| 0x83 | Gwen | 61.83% | 14x average |

### Why Only Grumpjaw Works
- Grumpjaw's 0x08 event is **uniquely abundant** (6000+ events per match)
- Other heroes' signature events have lower absolute counts
- When multiple heroes use similar event codes, discrimination fails

### Cross-Validation Importance
- Initial 17.76% accuracy was **misleading** (overfitting)
- LOOCV revealed true generalization: 4.17%
- Always use proper cross-validation for ML on small datasets

---

## Data Summary

| Metric | Value |
|--------|-------|
| Tournament Replays Analyzed | 11 |
| Total Players | 107-110 |
| Unique Heroes | 37 |
| Unique Event Codes | 250 |
| Heroes with Signatures | ~10 |
| Detectable with High Confidence | 1 (Grumpjaw) |

---

## Recommendations for Future Work

### 1. Payload Analysis
Current analysis only looks at event codes (byte 5). Analyzing event payloads
(bytes 6+) may reveal hero-specific patterns.

### 2. Sequence Analysis
Hero skills have specific cooldowns and combos. Temporal patterns in event
sequences might be more discriminative than raw counts.

### 3. Machine Learning
With more labeled data (>100 matches), supervised learning models (Random Forest,
Neural Networks) could potentially find complex patterns.

### 4. Alternative Data Sources
- Ability cooldowns from game data files
- Skill animation IDs
- Hero-specific item build patterns

### 5. Hybrid Approach
Combine multiple weak signals:
- Signature events (for Grumpjaw, etc.)
- Item purchases (weapon vs crystal)
- Attack patterns (0x0E for ranged)
- Team composition constraints

---

## Files Created

| File | Purpose |
|------|---------|
| `vg/core/event_pattern_detector.py` | Cosine similarity-based detection |
| `vg/core/signature_detector.py` | Signature event-based detection |
| `vg/analysis/skill_event_probe.py` | Event code analysis tool |
| `vg/analysis/full_event_analysis.py` | Complete event code analysis |
| `vg/analysis/validate_event_pattern_loocv.py` | LOOCV for ratio-based detection |
| `vg/analysis/validate_signature_loocv.py` | LOOCV for signature detection |
| `vg/output/skill_event_candidates.json` | Candidate event analysis results |
| `vg/output/full_event_analysis.json` | All event code analysis |
| `vg/output/loocv_validation_results.json` | LOOCV results (ratio-based) |
| `vg/output/signature_loocv_results.json` | LOOCV results (signature-based) |

---

## Conclusion

Hero detection from VGR replay binary data is fundamentally limited by:
1. Lack of explicit hero identifiers in accessible format
2. Similar event patterns across different heroes
3. Small sample size (37 heroes, only 1-7 samples each)

**Grumpjaw is the only hero that can be reliably detected** due to its unique
0x08 event signature. For other heroes, the current approaches do not provide
sufficient accuracy for practical use.

The 70% accuracy target was **not achieved**. Alternative approaches or
additional data sources would be needed to improve detection significantly.

---

*Document generated: 2026-02-14*
*Project: VG_REVERSE_ENGINEERING*
