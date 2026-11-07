# Marine perception findings

Real underwater crops were evaluated on sources excluded from the previously inspected dataset.
The earlier test set was used only as development data to choose a neighbor-voting method.

| Frozen method | Correct familiar | False unfamiliar alerts | Unknowns flagged |
| --- | --- | --- | --- |
| old-references-1nn | 67/93 | 4/93 | 26/71 |
| fresh-references-1nn | 79/93 | 1/93 | 7/71 |
| fresh-references-selected | 73/93 | 1/93 | 7/71 |

Selected neighbors: 5. Fresh split counts: {'test': 164, 'reference': 285, 'validation': 98}.
The first comparison changes references and calibration; the next isolates neighbor voting on the same new references.
No method was chosen using the new test outcomes. A worse result remains a result.
Unknown means unfamiliar to the reference collection, not a new species.
Source directories and thumbnail checks reduce leakage but do not establish independent dives.
Image-level Wilson intervals are in the JSON; correlated images can make these intervals optimistic.
Classification metrics do not establish improved mission discoveries. Use matched mission comparisons separately.
Images are local analysis material; do not publish restricted crops or this image gallery.

The selected model improved familiar classifications by 6/93 versus the old references, but flagged 19 fewer of the 71 unfamiliar images. It is experimental, and the operational default is unchanged.

Matched old/new/ideal checks ran 36 missions on the same 11-category pool across ridge, reversed and random ecology (two seeds each). All returned safely. Old and new vision produced identical true discovery counts in these runs; no exploration improvement was measured.
