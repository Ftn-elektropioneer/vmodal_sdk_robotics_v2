# Public robotics SDK release

The GitHub Actions workflow `.github/workflows/sdk_robot_test_release.yml`
publishes to `v-modal/vmodal_sdk_robotics` on `main`. Dispatch it with
`publish_sdk_robot=true` from the source branch to release the tested commit:

```bash
gh workflow run sdk_robot_test_release.yml --repo arita37/vmx_mobile --ref dev \
  -f publish_sdk_robot=true
```

Publication requires secret detection, offline tests on Python 3.10–3.13,
and package validation. The exported tree contains the root README, artwork,
LeRobot package, all root `docs/`, the Google Intrinsic guide, ROS bag backlog,
and the complete `todo/inside_ros/` and `todo/ranalysis/` designs. Diagrams from
`docs/assets/03_interface_rev3/` are also copied to
`todo/inside_ros/full/assets/03_interface_rev3/` so relocated design image links
resolve. The entire SDK tree passes secret detection. The publication job
compares the documentation, backlogs and diagrams with the candidate source.

The LeRobot public source includes all runtime modules (including
`reconciliation/` and markers), consumer guides, implementation notes, examples,
offline tests and their small synthetic fixtures, test and documentation scripts,
and the export filter itself. Local environment scripts, credentials, temporary
datasets, spool state, build outputs and generated API HTML are excluded. Wheels
contain only the lean runtime; source distributions retain tests and guides for
review. The root `todo/` directory contains the broader proposals; shipped local
behavior and external qualification gates are explained in
[the researcher workflow](../lerobot/docs/researcher_workflow.md).

Before pushing, the publication job installs the exported package and runs
`bash test.sh test` from a clean public source copy. This is the standalone suite;
the source monorepo offline jobs additionally run the SDK wire test using its
sibling `sdk_python/` checkout. Neither suite claims deployed cloud, decoder or
pinned LeRobot reader qualification.

The workflow records the source repository and commit in `RELEASE_METADATA`,
commits and tags public source atomically, then generates and publishes the API
reference. Credentials use the existing `INFISICAL_TOKEN` Actions secret and
Infisical `GH_TOKEN` key; no additional configuration is required.
