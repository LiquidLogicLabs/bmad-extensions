# Changelog

All notable changes to this project will be documented in this file. See [commit-and-tag-version](https://github.com/absolute-version/commit-and-tag-version) for commit guidelines.

## [3.7.1](https://github.com/LiquidLogicLabs/bmad-extensions/compare/3.7.0...3.7.1) (2026-11-16)


### Fixes

* **infra:** point every live URL at github.com/LiquidLogicLabs/bmad-extensions ([c5a732e](https://github.com/LiquidLogicLabs/bmad-extensions/commit/c5a732e25dfc1782d696069c52821bb5a6b9ff8f))


### Maintenance

* **deps-dev:** bump fast-xml-parser from 5.8.0 to 5.12.0 ([#1](https://github.com/LiquidLogicLabs/bmad-extensions/issues/1)) ([822cdc9](https://github.com/LiquidLogicLabs/bmad-extensions/commit/822cdc9ee09f04bc258611854d238b723bfbc3e6))
* **deps-dev:** bump smol-toml ([#4](https://github.com/LiquidLogicLabs/bmad-extensions/issues/4)) ([f664cf9](https://github.com/LiquidLogicLabs/bmad-extensions/commit/f664cf972071b13802af92677851d30a3aca118c))
* **deps:** bump astral-sh/setup-uv from 10.2.0 to 10.3.3 ([#2](https://github.com/LiquidLogicLabs/bmad-extensions/issues/2)) ([b6981e6](https://github.com/LiquidLogicLabs/bmad-extensions/commit/b6981e690249cf8a88ab6c7ac784b784e5b200be))
* **deps:** bump reviewdog/action-detect-secrets from 0.31.0 to 0.32.0 ([#3](https://github.com/LiquidLogicLabs/bmad-extensions/issues/3)) ([53b994c](https://github.com/LiquidLogicLabs/bmad-extensions/commit/53b994c415c7e955a71c70402a18cf64d6bbb13f))


### CI/CD

* **ci-cd:** configure CodeRabbit and Copilot reviews against this repo's rules ([874456d](https://github.com/LiquidLogicLabs/bmad-extensions/commit/874456d7256275b448b8b612e8e2169e1765e9b9))
* **ci-cd:** schedule Dependabot updates and merge passing patch/minor bumps ([b12dbc2](https://github.com/LiquidLogicLabs/bmad-extensions/commit/b12dbc2be4fb7ecc54b8f6d681a5fbda6dbbcfdb))

## [3.7.0](https://github.com/ravensorb/bmad-extensions/compare/3.6.0...3.7.0) (2026-11-16)


### Features

* **l3io-pm:** price each model's tokens at its own rate, and refuse naive timestamps ([91de947](https://github.com/ravensorb/bmad-extensions/commit/91de9473612c9ff48a7d17c0fe4e7b4ea62078c2))
* **l3io-pm:** record a mixed-model actual per model, and correct the Sonnet 5 rate ([ada8563](https://github.com/ravensorb/bmad-extensions/commit/ada856372cb2cab4fbe689ba5ed6b6dfe6e782c3))
* **l3io-pm:** stop at activation on a BMad v7 install ([c687afd](https://github.com/ravensorb/bmad-extensions/commit/c687afdf422f32108af952668759b6c3bfe80de3))


### Fixes

* **l3io-pm,l3io-util:** derive tool-root probes from BMad's default_roots() ([57e09aa](https://github.com/ravensorb/bmad-extensions/commit/57e09aa5a60955dee951587591c4b61f52023363))
* **l3io-pm,l3io-util:** find BMad 6.x skills in every tool's install directory ([f25166b](https://github.com/ravensorb/bmad-extensions/commit/f25166bb67a2c02576af677b4f3ce8c3c109c6aa))


### Documentation

* **infra:** add 3.7.0 upgrade notes ([e928b18](https://github.com/ravensorb/bmad-extensions/commit/e928b18f9e8d4b98d4fb757e34f046f6bd33b1d9))
* **l3io-pm:** propose a proof-based binding for the recovered-transcript fallback ([809a897](https://github.com/ravensorb/bmad-extensions/commit/809a897add08740435a630a84079df83fa7e8afc))

## [3.6.0](https://github.com/ravensorb/bmad-extensions/compare/3.5.2...3.6.0) (2026-10-27)


### Features

* **infra:** enforce the 1,500-line per-module cap in check 12 ([29a67c1](https://github.com/ravensorb/bmad-extensions/commit/29a67c1627ab7f76bfeec594e8314b43a32c3ea1))
* **l3io-pm:** bootstrap pm_status for script-path runs and widen gates to the package ([3d3565a](https://github.com/ravensorb/bmad-extensions/commit/3d3565a7d1069dad49af553b0490c776c2391e6c))
* **l3io-pm:** install pm-status as a package directory ([fca2011](https://github.com/ravensorb/bmad-extensions/commit/fca20110a7ade49427b15b035168247ea931dcad))
* **l3io-pm:** point every binding at the installed package ([9d8c675](https://github.com/ravensorb/bmad-extensions/commit/9d8c6752f014facb3dcd0385cc5317264968864c))


### Fixes

* **infra:** derive check 26's pm-status payload exemption from the sync deliveries ([4754875](https://github.com/ravensorb/bmad-extensions/commit/4754875bc69a2bbf28c85d4f15f74edf408a7cac))
* **infra:** make argparseSurface refuse a quietly-shrunk CLI surface ([a5f7fc5](https://github.com/ravensorb/bmad-extensions/commit/a5f7fc59210bb2bc02e72494fcf7ffca5c33e59a))
* **infra:** read choices=(TUPLE) as well as choices=[LIST] in the CLI surface ([755f0ed](https://github.com/ravensorb/bmad-extensions/commit/755f0edb7bcfff9824cf06bee577c72cae155928))
* **l3io-pm:** drop readerless facade re-exports and gate them ([a3ce16d](https://github.com/ravensorb/bmad-extensions/commit/a3ce16da7728b038d54b89148f61a125bc7f5fb8))
* **l3io-pm:** harden self-install's swap, rollback and shipped-hash coverage ([58e00a6](https://github.com/ravensorb/bmad-extensions/commit/58e00a6ce9558fca6772c106fbd6626b12ece5b1))
* **l3io-pm:** make the re-export reader gate walk the AST, not the text ([04ee40b](https://github.com/ravensorb/bmad-extensions/commit/04ee40b31fdc2a36ab3e12aa191b1e1b32dd2406))
* **l3io-pm:** probe the .agents/ tool root as well as .claude/ so v7 phases stop self-skipping ([8fcef71](https://github.com/ravensorb/bmad-extensions/commit/8fcef717736705e7f38283b841b44164fec00b39))
* **l3io-pm:** stop a concurrent self-install crashing on a swept staging tree ([f565c0f](https://github.com/ravensorb/bmad-extensions/commit/f565c0fe1ae855985f072a3823aaafebaf19261e))
* **l3io-util:** leave nothing behind when /l3io-doctor uninstall removes the payload ([6923a81](https://github.com/ravensorb/bmad-extensions/commit/6923a8158aa1c0b15cf95c8f993be7d4b59ad032))


### Refactoring

* **infra:** derive which file declares check 26's resolver section ([a2956b1](https://github.com/ravensorb/bmad-extensions/commit/a2956b1b3ecf01813b1f45c8f7d265df7ea34190))
* **l3io-pm:** extract pm_status.core, the package's dependency root ([32c6a87](https://github.com/ravensorb/bmad-extensions/commit/32c6a87574160f6285776a76a04691267b779c39))
* **l3io-pm:** extract pm_status.instructions, the marker engine and instruction-file sync ([550a777](https://github.com/ravensorb/bmad-extensions/commit/550a777bb50d847942657b456e7914e67de95042))
* **l3io-pm:** extract pm_status.issues, the deferred-issue lifecycle ([2eb88cd](https://github.com/ravensorb/bmad-extensions/commit/2eb88cdab2ffae391495747aae22829cd1de6585))
* **l3io-pm:** extract pm_status.metrics, the measurement layer ([61afb1a](https://github.com/ravensorb/bmad-extensions/commit/61afb1a7538532994b259754f341a84efcb65e49))
* **l3io-pm:** extract pm_status.nodes, the node layer ([4572f67](https://github.com/ravensorb/bmad-extensions/commit/4572f67e1679b094f46fa122a52f182436ac46f2))
* **l3io-pm:** extract pm_status.plan, the plan operations ([e4f0a59](https://github.com/ravensorb/bmad-extensions/commit/e4f0a5998cd528430566ca665a0e691b6aa3e19d))
* **l3io-pm:** extract pm_status.verbs, the status verbs ([b55e9dd](https://github.com/ravensorb/bmad-extensions/commit/b55e9dd3ccb430e9766c31f173efe35fc7d8f7cf))
* **l3io-pm:** give each module its own register(subparsers) ([23f23cd](https://github.com/ravensorb/bmad-extensions/commit/23f23cde12b68c916e8bea0d7cb8bfc4813502d5))
* **l3io-pm:** move pm-status.py into a pm_status package ([168b8ad](https://github.com/ravensorb/bmad-extensions/commit/168b8ade3f92c1f43e0cc9bf923f140018403f17))
* **l3io-pm:** relocate the seven core-bound items into core's region ([17671fd](https://github.com/ravensorb/bmad-extensions/commit/17671fd2b301ab0f342162fab7359e067adf844d))


### Documentation

* correct the pm-status package claims the live docs still make about a file ([8d37790](https://github.com/ravensorb/bmad-extensions/commit/8d37790157915582c51ad65019e56415e8c3c3ec))
* **infra:** correct the payload claim and record the binding-flip scope ([9d626d5](https://github.com/ravensorb/bmad-extensions/commit/9d626d5f82bd3803c11c7075222a4f33feacb406))
* **infra:** describe check:module rule 6 as the two payload shapes it checks ([d14aa23](https://github.com/ravensorb/bmad-extensions/commit/d14aa231a5bd64dc92201bb6aca1925024b014ce))
* **infra:** design pm-status.py as a package, adopting ADR-0001 Option B ([1811ddb](https://github.com/ravensorb/bmad-extensions/commit/1811ddbf6e51b0933494102ba06d1e6022c2af28))
* **infra:** plan the pm-status package split for 3.6.0 ([8c0f50a](https://github.com/ravensorb/bmad-extensions/commit/8c0f50adebbd3bc8e1d26ce9e85bd34064e7d7fa))
* **infra:** re-derive the extraction plan from a measured boundary analysis ([beb46c5](https://github.com/ravensorb/bmad-extensions/commit/beb46c581cd60b7677a94a957b4ad92b23b4a547))
* **infra:** scope the install contract to v6 and drop the symlink design ([7822060](https://github.com/ravensorb/bmad-extensions/commit/78220608fa745a43b356ea928725006c042fbb9c))
* **l3io-pm:** amend ADR-0001 for the package split, and correct the spec's record ([bbc638e](https://github.com/ravensorb/bmad-extensions/commit/bbc638e74d16caffb4ea25e185b2dfd34dc85a3c))
* **l3io-pm:** pin ADR-0001's symlink-atomicity claim to what was measured ([dc204ed](https://github.com/ravensorb/bmad-extensions/commit/dc204ed5a97f768ae6f5ed7e91032c70346fc0ed))
* **l3io-pm:** record v7's bmod.toml script declaration, which retires self-install at 4.0.0 ([9decb36](https://github.com/ravensorb/bmad-extensions/commit/9decb3665e2f8f320ff914697553f106a720d218))


### Testing

* **infra:** derive the check-bmb fixture line instead of pinning it, and record check 29's colon gap ([730fa38](https://github.com/ravensorb/bmad-extensions/commit/730fa3818667da98370ca0ed6acb974c94bbc768))
* **infra:** make check 26's exactly-one-declaration block inverted by tests ([f4f1aa0](https://github.com/ravensorb/bmad-extensions/commit/f4f1aa0cdff8d30000ff6d6eaaecd445a18cb9ea))
* **l3io-pm:** guard plan/'s core and nodes calls against private-copy bindings ([66a58f8](https://github.com/ravensorb/bmad-extensions/commit/66a58f86da0713ebed6c8dae19f1eba9b35db168))
* **l3io-pm:** guard reparent-story's doc rewrite against a private core copy ([a04dda5](https://github.com/ravensorb/bmad-extensions/commit/a04dda5f56837f4064be199cbdacb46839f6f77c))
* **l3io-pm:** guard the bootstrap prologue with a planted relative import ([5f06140](https://github.com/ravensorb/bmad-extensions/commit/5f061409ab357cfb6406a68add17fe8196f237ce))
* **l3io-pm:** pin package_root directly and guard the core re-exports ([7571c6c](https://github.com/ravensorb/bmad-extensions/commit/7571c6c5fdb3e7d85d8f4112e09d8d3e55e7dd02))
* **l3io-pm:** pin the 43 subcommands as a registration regression guard ([1473a68](https://github.com/ravensorb/bmad-extensions/commit/1473a686744ec3a37931ce3f97a104627494afde))
* **l3io-pm:** pin the OSError clause that keeps self-install from swallowing an interrupt ([58762ce](https://github.com/ravensorb/bmad-extensions/commit/58762ce56d2558ad6334f76e0fbdff35529ef0f8)), closes [#2](https://github.com/ravensorb/bmad-extensions/issues/2)

## [3.5.2](https://github.com/ravensorb/bmad-extensions/compare/3.5.1...3.5.2) (2026-10-23)


### Documentation

* **infra:** record that BMad owns and wipes _bmad/scripts on both lines ([9560a2b](https://github.com/ravensorb/bmad-extensions/commit/9560a2bbf125c1ce40a25f24be2bfc3a1ff70d50))

## [3.5.1](https://github.com/ravensorb/bmad-extensions/compare/3.5.0...3.5.1) (2026-10-22)


### Features

* **infra:** gate that every BLOCKED site is classified and its remedy named ([24a36ad](https://github.com/ravensorb/bmad-extensions/commit/24a36ad3a94f149b0b07f2e2d29bb685ca4e8fa8))
* **l3io-pm:** migrate and repoint state during activation ([0ccf9d5](https://github.com/ravensorb/bmad-extensions/commit/0ccf9d57c4de38696f5aa34cfd83c94038f53e80)) — the un-ignore remediation in that commit was reverted before release ([0e771d3](https://github.com/ravensorb/bmad-extensions/commit/0e771d3e4f6395d3c3411f5def43a24f294d5c4f)); a gitignored state root still halts
* **l3io-pm:** rebuild a missing or stale plan pointer instead of halting ([e150a85](https://github.com/ravensorb/bmad-extensions/commit/e150a851b69b590f240cdb628b0ddd6b40f44714))
* **l3io-pm:** remediate artifact-only stories instead of halting ([3a4dad1](https://github.com/ravensorb/bmad-extensions/commit/3a4dad11ce158140db88da82fed7ad74bc433925))
* **l3io-pm:** resolve an interrupted migration when the evidence is unambiguous ([6e01fe6](https://github.com/ravensorb/bmad-extensions/commit/6e01fe6f4fd7efab81f13102bb488433351f89d4))


### Fixes

* **infra:** check 36 tolerates qualified remedies and validates Class ([d8f175e](https://github.com/ravensorb/bmad-extensions/commit/d8f175e2c72ad8b560a4b52356f949449da1dc08))
* **l3io-pm:** bound the legacy epic-key match and state what the comparison proves ([64217a6](https://github.com/ravensorb/bmad-extensions/commit/64217a6befe7ef14478bd0ecf68da05367cd1620))
* **l3io-pm:** compare the gitignore path by component and from the project root ([2c32082](https://github.com/ravensorb/bmad-extensions/commit/2c320824d5cd1516e9fd68c08a2467e761e7b13c))
* **l3io-pm:** correct l3io-help's gitignore advisory and name the ignoring rule ([abe7ee3](https://github.com/ravensorb/bmad-extensions/commit/abe7ee33215de6a28c89d3c6e3a0219776611343))
* **l3io-pm:** decide gitignored-ness with check-ignore -q, not -v ([bd955bf](https://github.com/ravensorb/bmad-extensions/commit/bd955bfa75950ff7d548b2e148f5775cc0f55941))
* **l3io-pm:** fail closed on an empty toplevel and append to the validated path ([e92a494](https://github.com/ravensorb/bmad-extensions/commit/e92a4946d91808e1608bf1f8746a5cd999e3484c))
* **l3io-pm:** make the unreadable-listing guard a variable, not printed output ([51509d2](https://github.com/ravensorb/bmad-extensions/commit/51509d2c23cb2399aca009ed727defd10e28abea))
* **l3io-pm:** refuse to append through a symlinked .gitignore ([e36b78c](https://github.com/ravensorb/bmad-extensions/commit/e36b78cfd88d0155c7396b9d4ca763a699755cfa))
* **l3io-pm:** restrict the gitignore remediation to a work-tree .gitignore ([a533645](https://github.com/ravensorb/bmad-extensions/commit/a533645c99825d3042caa9bcd156457a573420d3))
* **l3io-pm:** revert gitignore remediation to a halt, fix bootstrap and message accuracy ([0e771d3](https://github.com/ravensorb/bmad-extensions/commit/0e771d3e4f6395d3c3411f5def43a24f294d5c4f))
* **l3io-pm:** use placeholders for the illustrative paths in the gitignore guard ([fe9f7eb](https://github.com/ravensorb/bmad-extensions/commit/fe9f7ebcd829cd7ed681e8188cedf2d6da85e794))


### Documentation

* **infra:** correct the spec's gitignore remedy to match the implementation ([a459c98](https://github.com/ravensorb/bmad-extensions/commit/a459c98c0994e1e06a2255d65ac444910cb78c99))
* **infra:** correct the spec's multi-layout remedy and scope the authority note to section 4 ([7704a87](https://github.com/ravensorb/bmad-extensions/commit/7704a879c929da8e302aee52dc2d8328fd323fa6))
* **infra:** name the unbuilt verb by role in ADR-0012 ([ee15da3](https://github.com/ravensorb/bmad-extensions/commit/ee15da36332902a5dea37b8660d9177637c9d24a))
* **infra:** name the unbuilt verb by role in ADR-0012, both places ([60c999b](https://github.com/ravensorb/bmad-extensions/commit/60c999b4bffab14d1395c0749146a79438f4882b))
* **infra:** plan auto-remediation of orchestrator halts ([28df9b5](https://github.com/ravensorb/bmad-extensions/commit/28df9b5629e47bd5c8a342b1de9ac807ef66f450))
* **infra:** record the auto-remediation decision and fix two stale claims ([978d7b5](https://github.com/ravensorb/bmad-extensions/commit/978d7b53185abdaac6a4ce382e1a9024a1b32255))
* **l3io-pm:** classify remediation rows and state the authoring rules ([2d304c9](https://github.com/ravensorb/bmad-extensions/commit/2d304c96b815eb2a66579be9373addc497fa0e68))
* **l3io-pm:** correct troubleshooting and the remediation contract against the shipped halts ([49bdf05](https://github.com/ravensorb/bmad-extensions/commit/49bdf05ee0121358ebe9256d127dc621b33a8615))
* **l3io-pm:** share one rebuild attempt across the plan-pointer sites ([47485e4](https://github.com/ravensorb/bmad-extensions/commit/47485e4617ad5d4fa8c3f34bd2b5933b4782c6cc))


### Testing

* **infra:** let the check-12 boundary test run when the file is already at the cap ([76636d4](https://github.com/ravensorb/bmad-extensions/commit/76636d492e93db10fd2779fb287e2449868593af))
* **infra:** make check 36 reject a remedy named only inside its halt ([ad76d39](https://github.com/ravensorb/bmad-extensions/commit/ad76d39b5548c16817d4d9e2e2c537649a15be18))
* **infra:** pin the gitignore sibling example on its placeholder form ([a6c8088](https://github.com/ravensorb/bmad-extensions/commit/a6c8088931833481bd3ce3071bc6d1a0404f488f))
* **infra:** plant the discovery probe in a temp root, not the real tree ([764567f](https://github.com/ravensorb/bmad-extensions/commit/764567fe194cb7965e1b0d6c32de999f112cc20e))

## [3.5.0](https://github.com/ravensorb/bmad-extensions/compare/3.4.5...3.5.0) (2026-10-21)


### Features

* **l3io-pm:** recover a session transcript by elimination when the env is silent ([aba1ee4](https://github.com/ravensorb/bmad-extensions/commit/aba1ee446747de75c4f52696540248ff1d08bc7c))
* **l3io-util:** detect the BMad generation and probe the .agents skill root ([7ce9719](https://github.com/ravensorb/bmad-extensions/commit/7ce9719db96f7a02118ee6bfd7c3debfd102660a))
* **l3io-util:** read v7 module records from bmod.toml ([ac3ca90](https://github.com/ravensorb/bmad-extensions/commit/ac3ca909eae6cbf7e70cf64c4eca84a98a87fe95))
* **l3io-util:** verify degraded on v7 and exit 6 instead of 4 ([9ca7698](https://github.com/ravensorb/bmad-extensions/commit/9ca769804c7171359ec7f8fb7fb3939f574798be))


### Fixes

* **l3io-pm:** keep the verified transcript and skip unusable candidates in recovery ([d529c50](https://github.com/ravensorb/bmad-extensions/commit/d529c5096cb5bd50ea156ab2d9eeb8c49c20cba8))
* **l3io-pm:** require a record inside the dispatch window before recovering a transcript ([784474e](https://github.com/ravensorb/bmad-extensions/commit/784474e453f6e678dbe37fb2f5452aeef25997fe))
* **l3io-pm:** serialise the usage window in --format json ([9b84bed](https://github.com/ravensorb/bmad-extensions/commit/9b84bedfdc3de6a186e86f54bbc95bf7211b4ca4))
* **l3io-util:** give health-check Check 20 an exit-6 arm for BMad v7 ([1266618](https://github.com/ravensorb/bmad-extensions/commit/1266618e5c7129e6f1f2964d5630a1ea4c81fad4))
* **l3io-util:** stop claiming every missing v7 skill was removed ([20b8dd4](https://github.com/ravensorb/bmad-extensions/commit/20b8dd4598baea4ece39f79b6d2a12cc6261f14b))
* **l3io-util:** stop health-check telling the doctor to discard baseline_drift on v7 ([ff33e49](https://github.com/ravensorb/bmad-extensions/commit/ff33e4965e85fd3267ae7951ed57bb4fca546102))


### Refactoring

* **l3io-util:** share one bmod.toml walk between both readers ([edb12ae](https://github.com/ravensorb/bmad-extensions/commit/edb12aecb49ae498d9f83492348fd82f45adea05))


### Documentation

* correct the suite count and record two ordering and probe deferrals ([cd9406d](https://github.com/ravensorb/bmad-extensions/commit/cd9406ddc1d8c1d22df5bec197b07e636d0bb025))
* **infra:** add transcript-resolution fallback, correct the telemetry risk ([beebed4](https://github.com/ravensorb/bmad-extensions/commit/beebed41745f942d4a810ee7e9772e71b1415070))
* **infra:** design auto-remediation of orchestrator halts ([29ef636](https://github.com/ravensorb/bmad-extensions/commit/29ef63677606ba4e2c5119ae46ca43443625741a))
* **infra:** design the BMad v7 layer ([a3d5838](https://github.com/ravensorb/bmad-extensions/commit/a3d5838b403a40523ff71e9a36d08ff956fa58ef))
* **infra:** plan the 3.5.x BMad v7 bridge ([739abcf](https://github.com/ravensorb/bmad-extensions/commit/739abcfbc95ba9bee1773e55210ed839856f11fd))
* **infra:** re-measure the v7 spec against 61e01f8, add a drift log ([fbc5e33](https://github.com/ravensorb/bmad-extensions/commit/fbc5e3323b928e15dc6d8cc1f5a9097595e3177e))
* **l3io-pm:** list all seven step files in the .agents probe asymmetry ([d764e33](https://github.com/ravensorb/bmad-extensions/commit/d764e3341d4674f833fed9a959519c4f3b653937))
* **l3io-pm:** stop claiming the doctor probe matches resolve() ([8ff65db](https://github.com/ravensorb/bmad-extensions/commit/8ff65db72a6484482bdad4766a9bd71ff7281680))
* warn about bmad migrate on l3io projects, fix stale claims, record bridge deferrals ([7a6d044](https://github.com/ravensorb/bmad-extensions/commit/7a6d0448d3d48ed480567733a2abe48b0d3dc97e))


### Testing

* **l3io-pm:** pin the transcript span rule independently of the in-window guard ([013da10](https://github.com/ravensorb/bmad-extensions/commit/013da104c24e3dfd52e5733d721e37b9242dda7f))
* **l3io-util:** repoint HOME for in-process generation tests ([1a9018e](https://github.com/ravensorb/bmad-extensions/commit/1a9018ef83f1e27f04a297a2b65d82d5022bd81f))

## [3.4.5](https://github.com/ravensorb/bmad-extensions/compare/3.4.4...3.4.5) (2026-10-12)


### Fixes

* **l3io-pm:** refuse a repeated --key in promote-issue instead of deduping ([12803ad](https://github.com/ravensorb/bmad-extensions/commit/12803ad036fcf0a78a0c09601cd617eee1f6f8b4))
* **l3io-pm:** the repeated-key refusal says what to DO, not just what is wrong ([c8ce17c](https://github.com/ravensorb/bmad-extensions/commit/c8ce17ca803b32a42f31612a836408f0bc450154))


### Documentation

* close four gaps a documentation audit found ([219d249](https://github.com/ravensorb/bmad-extensions/commit/219d249215af757421ae5ddfb5f814c12f980875))
* **infra:** record that check:docs asserts surface, never behaviour ([924450d](https://github.com/ravensorb/bmad-extensions/commit/924450d7179ae13546666e85c0c9da7fb719a146))
* **upgrading:** name the 3.4.5 release the placeholder was waiting for ([82c0c54](https://github.com/ravensorb/bmad-extensions/commit/82c0c540cc82c0e1b72396e766cb6746fa772ecb))


### CI/CD

* least-privilege permissions on checks.yml ([d2b7671](https://github.com/ravensorb/bmad-extensions/commit/d2b767189eeb3d524249861c5b7598744ec9d4e6))
* least-privilege permissions on reviewdog.yml ([4681c55](https://github.com/ravensorb/bmad-extensions/commit/4681c556dc3890ef3f2f10342cfb35abac676981))

## [3.4.4](https://github.com/ravensorb/bmad-extensions/compare/3.4.3...3.4.4) (2026-10-12)


### Fixes

* **l3io-pm:** refresh the l3io block left in another harness's file ([9d68829](https://github.com/ravensorb/bmad-extensions/commit/9d6882952bcd604a815f4762ba457330b457a897))
* **l3io-pm:** refuse a non-list depends_on instead of dropping the edge ([4edfe93](https://github.com/ravensorb/bmad-extensions/commit/4edfe9364ed41151d3cd8ec64b6fe252c3b21e99))


### Documentation

* **infra:** disarm the NUMBER_WORDS trap and correct a stale gap note ([ef783fa](https://github.com/ravensorb/bmad-extensions/commit/ef783fac395d024693f957d6d97694a3a31e5306))
* **infra:** record why check 35 stays scoped to forwarders ([27e6ba4](https://github.com/ravensorb/bmad-extensions/commit/27e6ba4182027e3a64c406c8259b6131a413b3cc))
* the l3io-util-cleanup forwarder was removed in 3.0.0, not "next release" ([433c88e](https://github.com/ravensorb/bmad-extensions/commit/433c88eead3b79fa1077f849fc6afcdf1fcf3db7))
* **upgrading:** fold the two pending entries into one 3.4.4 ([30513d7](https://github.com/ravensorb/bmad-extensions/commit/30513d7a7ec97e815a84e959d06d508ee47a2ecb))


### Testing

* **infra:** check 35 — a forwarder's rename version must name a real release ([c05ba58](https://github.com/ravensorb/bmad-extensions/commit/c05ba58aa72e0f9f0faefdccb3736f96f2d26372))
* **infra:** scoped type gate for pm-status.py's accessor contracts ([ccf8073](https://github.com/ravensorb/bmad-extensions/commit/ccf80730dc513bfd14593b940ceb5c2fd7578800))
* **l3io-pm:** adopt three improvements found by reading the peer tree directly ([4171cee](https://github.com/ravensorb/bmad-extensions/commit/4171cee0cfc1a8d4fc71569c4687f139ee2d9846))
* **l3io-pm:** close the resolve-issue branch gaps, restore a cross-reference ([229d781](https://github.com/ravensorb/bmad-extensions/commit/229d7819d01e5c4d5026dea8a20377252b520b95))
* **l3io-pm:** close the schedule-issue branch gaps ([ca9ccda](https://github.com/ravensorb/bmad-extensions/commit/ca9ccdae07770be80d010328770d97d2e601e921))
* **l3io-pm:** close the set-actual refusal gaps ([ae130d8](https://github.com/ravensorb/bmad-extensions/commit/ae130d80d48f744c35b925a936e8755a162a6d81))
* **l3io-pm:** correct the advisory measurement, and assert both locks ([e7d1577](https://github.com/ravensorb/bmad-extensions/commit/e7d1577a0e6f4a8789bae7026ea0ad3d95e7665b))
* **l3io-pm:** drop two redundant set-actual tests, weaker than what existed ([9afcfaf](https://github.com/ravensorb/bmad-extensions/commit/9afcfaf22649e283a8fb8789d171aac71a5f563f))
* **l3io-pm:** pin both of schedule-issue's advisory refusal passes ([e1e50e8](https://github.com/ravensorb/bmad-extensions/commit/e1e50e8cda27cafccabd2a3ed419d9da257b397a))
* **l3io-pm:** promote's advisory refusal pass, and the key-dedup characterisation ([6c226b2](https://github.com/ravensorb/bmad-extensions/commit/6c226b262ded32d1054851c682e38524029589ae))


### CI/CD

* enable Dependabot alerts and security updates; audit.yml stays, weekly ([fe387cb](https://github.com/ravensorb/bmad-extensions/commit/fe387cbbb9fe6bfc58774c2ec2661062da227bfd))

## [3.4.3](https://github.com/ravensorb/bmad-extensions/compare/3.4.2...3.4.3) (2026-10-12)


### Fixes

* **l3io-pm:** repoint every backlog reference a re-key invalidates ([dea48ea](https://github.com/ravensorb/bmad-extensions/commit/dea48ea196324094d644c2695e58ae75a47e285f))

## [3.4.2](https://github.com/ravensorb/bmad-extensions/compare/3.4.1...3.4.2) (2026-10-11)


### Fixes

* **l3io-pm:** reparent-story crashed mid-write on any project with a backlog ([028d951](https://github.com/ravensorb/bmad-extensions/commit/028d9518aa1437d92b6e0199e36aad176a233eb5))


### Documentation

* **upgrading:** the reparent-story crash, and the residue it leaves ([65094c3](https://github.com/ravensorb/bmad-extensions/commit/65094c369a7d46916c925837cb7841f565455448))

## [3.4.1](https://github.com/ravensorb/bmad-extensions/compare/3.4.0...3.4.1) (2026-10-11)


### Features

* **l3io-pm:** lanes — the field, the schema, and the cross-lane finding ([8c530c5](https://github.com/ravensorb/bmad-extensions/commit/8c530c5996abfb67d76dd312e2f528809850b440))
* **l3io-pm:** setup asks the lane mode, and plan-graph proposes a partition ([bbe8ee7](https://github.com/ravensorb/bmad-extensions/commit/bbe8ee7a2e320dda2c28cb65f24b00f165dacf6b))
* **l3io-pm:** the lanes mode, the protocol, and the union merge driver ([639d392](https://github.com/ravensorb/bmad-extensions/commit/639d392952a054d84d740e6ba99edd092507cffc))


### Fixes

* **l3io-pm:** the lanes row's followed-by names a capability that exists ([ed15c07](https://github.com/ravensorb/bmad-extensions/commit/ed15c0753e65593a7439be0be5a8a282f1b119a3))


### Documentation

* lanes reach the docs, and a shipped gap the sweep found ([af1bb3d](https://github.com/ravensorb/bmad-extensions/commit/af1bb3d8d6a5857797f32bc9dca30c606b276759))
* **plan:** parallel lanes — seven tasks, with the three questions answered ([f02f42c](https://github.com/ravensorb/bmad-extensions/commit/f02f42c3a3aab0b374ae9f5682fc5f0ab6d4f24c))
* **spec,plan:** lanes — acceptance criterion, measured premise, two specified tasks ([c48f107](https://github.com/ravensorb/bmad-extensions/commit/c48f107483e5d8761267c428fb47081df3c93216))
* **spec,plan:** the lane mode is asked at setup, never inferred ([a334d25](https://github.com/ravensorb/bmad-extensions/commit/a334d25425d9f0af9d5ea8ca77880dbaa9142c0e))
* **spec:** parallel lanes — one epic, one lane ([16a5bfd](https://github.com/ravensorb/bmad-extensions/commit/16a5bfd575291a90b1e3608635044535f994bba5))
* **upgrading:** uninstall was incomplete on 3.2.5–3.3.1, and said otherwise ([3d438dd](https://github.com/ravensorb/bmad-extensions/commit/3d438ddce3cc7ef2695d2a21900f59b4b5f74b4c))

## [3.4.0](https://github.com/ravensorb/bmad-extensions/compare/3.3.1...3.4.0) (2026-10-11)


### Features

* **l3io-pm:** balancing pass that cannot undo the structural one ([c257022](https://github.com/ravensorb/bmad-extensions/commit/c257022befaa80a09da90df161bb61017ccb06ba))
* **l3io-pm:** check the plan's shape before paying to estimate it ([c4ecfed](https://github.com/ravensorb/bmad-extensions/commit/c4ecfed1a95fdaae26017141beac4c4320063003))
* **l3io-pm:** plan-graph.py — the phase order is computed, not recited ([00bcff2](https://github.com/ravensorb/bmad-extensions/commit/00bcff228439c3d5f741ea8099a2485b6f9265eb))
* **l3io-pm:** reorg optimises structure it can change, not effort it cannot ([51b0179](https://github.com/ravensorb/bmad-extensions/commit/51b017991a9c40f647faec2b87ae5b9724a6b6b4))
* **l3io-pm:** reorg's parallelism gain actually lands, and no step asks for a hand edit ([f31d463](https://github.com/ravensorb/bmad-extensions/commit/f31d463b87c9a436f61460b509b183638bfda0f2))


### Fixes

* **infra:** the payload manifest covers what ships, not what was synced ([24dc801](https://github.com/ravensorb/bmad-extensions/commit/24dc8010c9b26e51555d961629389f88704b8636))
* **l3io-pm:** a plan run with nothing in it no longer reports green ([8ed7f6d](https://github.com/ravensorb/bmad-extensions/commit/8ed7f6df572be9d6e54d0c0734cf63c380ebaa6b))
* **l3io-pm:** close two dependency holes that let a plan schedule work wrongly ([f8cc2bb](https://github.com/ravensorb/bmad-extensions/commit/f8cc2bbad248f6bec8e3adfd067627b864ea9d45))
* **l3io-pm:** compute the critical path after the estimates it is made of ([eda7bb3](https://github.com/ravensorb/bmad-extensions/commit/eda7bb39472499bb911122432f41438a0b0b7f1c))
* **l3io-pm:** plan's readiness check now grades what its own enricher writes ([7af1c41](https://github.com/ravensorb/bmad-extensions/commit/7af1c41e01f075d1bb1c4c1a8ca9f013da7d60c3))


### Documentation

* **plan:** every recommended action gets a command that exists ([f089690](https://github.com/ravensorb/bmad-extensions/commit/f0896902bd8a4c12b769958305be41c0b583d749))
* **plan:** manifest covers what ships; fold phases into plan-graph.py ([c9abf87](https://github.com/ravensorb/bmad-extensions/commit/c9abf87133ef8300fcdb8a53c54d227f1e045a01))
* **plan:** reorg's objective is dependency structure, not effort ([47b54ce](https://github.com/ravensorb/bmad-extensions/commit/47b54ce8f3cc0488f963f6a902cc7a7e45220758))
* **plan:** the human decides, the agent edits — no carve-outs ([2234d06](https://github.com/ravensorb/bmad-extensions/commit/2234d062e2995f561d1f19541089d6fbd076e7e8))
* **plan:** the line cap is a tripwire, not a design input ([61edb57](https://github.com/ravensorb/bmad-extensions/commit/61edb57f078021d98afb7b6c0491e7843db0044e))
* **plan:** validate by the gates that already exist, and say what cannot be ([d53d7dc](https://github.com/ravensorb/bmad-extensions/commit/d53d7dce6d13a128951bbf00a94ba60a698c5f2f))


### Maintenance

* **infra:** move the pinned baseline to BMad 6.12.2, on evidence ([ad61439](https://github.com/ravensorb/bmad-extensions/commit/ad6143937bced209bdafce0a1134889636dec0bc))

## [3.3.1](https://github.com/ravensorb/bmad-extensions/compare/3.3.0...3.3.1) (2026-10-09)


### Features

* **l3io-pm:** a plan run now says when its own shape could be better ([3b965a6](https://github.com/ravensorb/bmad-extensions/commit/3b965a6f073cd325e1d59934dd260808bc0f1c66))


### Documentation

* document reorg and the instruction block where people actually read ([7e6507b](https://github.com/ravensorb/bmad-extensions/commit/7e6507b8222091258f8e1e375d82efc89c347f0f))

## [3.3.0](https://github.com/ravensorb/bmad-extensions/compare/3.2.6...3.3.0) (2026-10-09)


### Features

* **ci-cd:** gate on npm audit, on push and on a daily schedule ([b4a05c0](https://github.com/ravensorb/bmad-extensions/commit/b4a05c07f00a4db22eb140fd5c659a4f868aa882))
* **l3io-pm:** /l3io-plan reorg, end to end — journal, undo, sync reconciliation ([c58e8ea](https://github.com/ravensorb/bmad-extensions/commit/c58e8eaa7bbec11ae03c08342a5de16e5ec4642d))
* **l3io-pm:** derive reorg operations from the target, in a safe order ([89ab4be](https://github.com/ravensorb/bmad-extensions/commit/89ab4be9ae99432b06a33c616a1d23806e1d8ce1))
* **l3io-pm:** marker engine for the agent instruction block ([31178e4](https://github.com/ravensorb/bmad-extensions/commit/31178e47c5eeb0f06baf84382db18f7186274d82))
* **l3io-pm:** offer the instruction block once per harness ([6a2043e](https://github.com/ravensorb/bmad-extensions/commit/6a2043eafb544ea1636a4eb1e4f59a67fc5493ae))
* **l3io-pm:** reparent-story moves a planned story between sprints, re-keying it ([af7640d](https://github.com/ravensorb/bmad-extensions/commit/af7640d02656bb6b592cddee12caf8d032e616cc))
* **l3io-pm:** retire-epic archives an epic and records why ([5e252de](https://github.com/ravensorb/bmad-extensions/commit/5e252deb8cb19836e22782a354fab16025fe1fd4))
* **l3io-pm:** ship the agent instruction block body as a shared asset ([c88bb6e](https://github.com/ravensorb/bmad-extensions/commit/c88bb6eeab3314939f6e22fee8824fd21c66d419))
* **l3io-pm:** sync-agent-instructions writes the block into the harness file ([fca62fe](https://github.com/ravensorb/bmad-extensions/commit/fca62fe456f5404086d0511ef770b4fc02f075cc))
* **l3io-pm:** the reorg analyzer, and dump-plan to feed it ([58ff106](https://github.com/ravensorb/bmad-extensions/commit/58ff1063d3340a4a2f2f85c724498490a1dbad1c))
* **l3io-pm:** the reorg target validator — drift is unrepresentable, not merely rejected ([66ea704](https://github.com/ravensorb/bmad-extensions/commit/66ea704dd38a064d1d39b30cd2ff58e16eaf748c))
* **l3io-pm:** write an l3io instruction block into the project's AI instruction file ([a1743ba](https://github.com/ravensorb/bmad-extensions/commit/a1743ba0182a7faa7fc2384bcb0fba4fe8afb990))
* **l3io-util:** maintain the instruction block across install, upgrade and clean ([af23710](https://github.com/ravensorb/bmad-extensions/commit/af2371068578d1534397b26e97e04c4c315d4b19))


### Fixes

* **infra:** check 31 could not see the one place the defect actually was ([4dffadd](https://github.com/ravensorb/bmad-extensions/commit/4dffadd7131bcc59e32e51350add967e28e0fec4))
* **l3io-pm:** gitignore the agent-instruction lock file under _bmad ([ae2a472](https://github.com/ravensorb/bmad-extensions/commit/ae2a47280e9d03fad885af2392faf6d23aa3967b))
* **l3io-pm:** marker engine touches only the seam, normalises CRLF bodies, pairs fences by kind ([ff37b5e](https://github.com/ravensorb/bmad-extensions/commit/ff37b5ec1cafa730fc16798414ee284b9aa63020))
* **l3io-pm:** story keys come from a high-water allocator, never from the disk alone ([de2f730](https://github.com/ravensorb/bmad-extensions/commit/de2f7303f871e2683db1d3bb00e08b11d6ed05e9))
* **l3io-pm:** sync-agent-instructions no longer damages the user's file ([9876180](https://github.com/ravensorb/bmad-extensions/commit/9876180110992427508010b539291de8e14b8265))
* **l3io-pm:** use removeprefix in remove_block ([fbc2ac4](https://github.com/ravensorb/bmad-extensions/commit/fbc2ac4b94bc91564da94d7ca67b5b0e24f66351))
* **l3io-util:** cite the runtime detection procedure and order block removal before payload sweep ([c70db4e](https://github.com/ravensorb/bmad-extensions/commit/c70db4eea9d46dbfb149cc8a1eb42d3e0d602ad2))
* **l3io-util:** gate the upgrade apply behind the confirmation and bind runtime and file ([b061461](https://github.com/ravensorb/bmad-extensions/commit/b061461677ed646c0143a8c502b632c33de596a0))


### Refactoring

* **infra:** one definition of what a DEPRECATED forwarder is ([38de8dc](https://github.com/ravensorb/bmad-extensions/commit/38de8dcaa67229ce6ba3aeeac083e0b59c5d25e0))


### Documentation

* **plan:** agent instruction block — implementation plan ([13185a1](https://github.com/ravensorb/bmad-extensions/commit/13185a1573321bc34c5b223e7e91cb9f3e974a83))
* **plan:** close an unbalanced fence that hid Tasks 4 and 5 ([ccef229](https://github.com/ravensorb/bmad-extensions/commit/ccef2299bb3486eade1e7ded4722153f9de354e9))
* **readme:** l3io-plan now ships a scripts/ directory ([d0c17a4](https://github.com/ravensorb/bmad-extensions/commit/d0c17a478afdeec1435605f8f9eb69382732b878))
* **spec:** /l3io-plan reorg — design, with acceptance criteria and a complexity assessment ([7080de2](https://github.com/ravensorb/bmad-extensions/commit/7080de27d932d9767b76c0ddee3a8e8cd204b31b))
* **spec:** agent instruction block — design ([747aba2](https://github.com/ravensorb/bmad-extensions/commit/747aba267cfe496054b95ba187d765092d42d3ab))
* **spec:** reorg proposes a target placement, not operations ([f27dbc2](https://github.com/ravensorb/bmad-extensions/commit/f27dbc2356f23e90a16e499575ca32ca112f550f))
* **spec:** the reorg output is the proposed plan, not a changelog of moves ([7de2d09](https://github.com/ravensorb/bmad-extensions/commit/7de2d09308fa85009af91d78b19a1bc8833e9178))


### Maintenance

* **deps:** handlebars 4.7.9 -> 4.7.10, closing three critical advisories ([327d453](https://github.com/ravensorb/bmad-extensions/commit/327d4539c8ab28b50acf4a721ef3cb313478c697))


### Testing

* **infra:** derive check 26's plant line instead of hardcoding it ([7b4d630](https://github.com/ravensorb/bmad-extensions/commit/7b4d63043e41dc7805f853b33d7fac0e6b7f2f8f))
* **l3io-pm:** stop pinning migrate-adrs' commit failure to one racy cause ([4da5479](https://github.com/ravensorb/bmad-extensions/commit/4da5479935ff4079f526d12b2331380f06d566ba))

## [3.2.6](https://github.com/ravensorb/bmad-extensions/compare/3.2.5...3.2.6) (2026-10-04)


### Fixes

* **infra:** exempt a deprecated forwarder's missing-entry, on evidence ([ea20a03](https://github.com/ravensorb/bmad-extensions/commit/ea20a03b523e96095b938980a670c1f30aeea1f4))
* **infra:** move the pinned baseline twin to 6.12.1 ([8dd0db4](https://github.com/ravensorb/bmad-extensions/commit/8dd0db45b288b4ea8b8c637cd30467ff77c23bb3))
* **l3io-pm:** don't index YAML frontmatter as a spec section; report BMad version ([7c2d991](https://github.com/ravensorb/bmad-extensions/commit/7c2d991d0f625cd5bcece3182245d8261d412a37))


### Maintenance

* **deps:** bump brace-expansion 1.1.18 -> 1.1.21 (3 DoS advisories) ([9cacdc1](https://github.com/ravensorb/bmad-extensions/commit/9cacdc1361728a3b02bc3a17bd9b9abd60e0f199))

## [3.2.5](https://github.com/ravensorb/bmad-extensions/compare/3.2.4...3.2.5) (2026-10-04)


### Features

* install.sh — one entry point that picks the right BMad command ([e20c8b1](https://github.com/ravensorb/bmad-extensions/commit/e20c8b1488c49b8aef9b86f85d9b1662b2b6be43))
* **l3io-pm:** schedule-issue attaches a backlog item to an existing story ([fb362a5](https://github.com/ravensorb/bmad-extensions/commit/fb362a5e527b2d8d8503a02b879c92755ecf7951))
* **l3io-util:** a version mode that answers "which l3io am I on?" ([d960049](https://github.com/ravensorb/bmad-extensions/commit/d960049521af63f719a81d2da277ece00a24d052))


### Fixes

* **l3io-pm:** canonicalise dispatch keys on read, not only on write ([a38424c](https://github.com/ravensorb/bmad-extensions/commit/a38424c17e131a36a5b8586acc3d9e90cf266d26))
* **l3io-pm:** two more event readers crashed on a malformed field ([41b89a8](https://github.com/ravensorb/bmad-extensions/commit/41b89a8bbece76db90ea2063490d75078efe26f1))
* **l3io-util:** check-pm-status reports the version, not argparse's banner ([204dbde](https://github.com/ravensorb/bmad-extensions/commit/204dbde3a11d98dc7eef946b837aaa8442fd2e1e))
* **l3io-util:** install was claimed by two routing rows with no tie-break ([b972838](https://github.com/ravensorb/bmad-extensions/commit/b972838f670276e87c486da4bde2f3609e1a360e))


### Documentation

* correct two instruction-file claims that had gone false ([db49743](https://github.com/ravensorb/bmad-extensions/commit/db49743f2cc4dac0da2a5f18e192b4d59e58ad0b))
* **infra:** the in-repo handoff stated a release number and went stale again ([4a35c7e](https://github.com/ravensorb/bmad-extensions/commit/4a35c7e279a9d07b391f4ed23ec0365730e5d568))
* **readme:** state the trade in omitting --modules, not just the benefit ([efee33c](https://github.com/ravensorb/bmad-extensions/commit/efee33c427638bc5fdd865529fba9d1642722c20))
* **readme:** the install command is first-install only; upgrading differs ([58e92af](https://github.com/ravensorb/bmad-extensions/commit/58e92afe210db879ce486d5a339b8c9e44a18221))

## [3.2.4](https://github.com/ravensorb/bmad-extensions/compare/3.2.3...3.2.4) (2026-10-03)


### Fixes

* **l3io-util:** harvest-debt searched nothing and called it a clean tree ([bd077b6](https://github.com/ravensorb/bmad-extensions/commit/bd077b6df795125f1f2e4a2eed4f9acd1ff22435))

## [3.2.3](https://github.com/ravensorb/bmad-extensions/compare/3.2.2...3.2.3) (2026-10-03)


### Fixes

* **l3io-pm:** store epic and sprint canonically, at every write site ([43c0296](https://github.com/ravensorb/bmad-extensions/commit/43c0296d2dde4d104f60da3b8aa546885d759833))


### Documentation

* **infra:** record the rename's two lessons and two consumer requests ([2f7f11a](https://github.com/ravensorb/bmad-extensions/commit/2f7f11add47d0d1bd62dbd48835eed8b416d7661))


### Maintenance

* **infra:** raise the pm-status.py line cap to 10,000; retire Option C ([16a662e](https://github.com/ravensorb/bmad-extensions/commit/16a662ea359fed5661aaab6e4414fce52fe34cb8))

## [3.2.2](https://github.com/ravensorb/bmad-extensions/compare/3.2.1...3.2.2) (2026-10-02)


### Features

* **l3io-pm:** work_type selects vocabulary, not whether a story is reviewed ([1cd94a9](https://github.com/ravensorb/bmad-extensions/commit/1cd94a909119e2c8a019e4a9f491dc364b32ccdd))

## [3.2.1](https://github.com/ravensorb/bmad-extensions/compare/3.2.0...3.2.1) (2026-09-30)


### Documentation

* **infra:** the payload manifest covers synced files, not shipped ones ([53284c5](https://github.com/ravensorb/bmad-extensions/commit/53284c5a0c41fd8bcd8de1c90c62ecf49d6ec23f))

## [3.2.0](https://github.com/ravensorb/bmad-extensions/compare/3.1.8...3.2.0) (2026-09-30)


### Features

* **infra:** check that a deprecated forwarder actually forwards ([cdde623](https://github.com/ravensorb/bmad-extensions/commit/cdde623af6e53201366c230331a272c5e392641e))


### Fixes

* **infra:** stop check-docs truncating its report, and stop it re-walking the same shell ([ea20356](https://github.com/ravensorb/bmad-extensions/commit/ea20356fcbfd5fc2982d21679912a0f86b360c82))
* **infra:** stop the other four gates truncating their reports ([f102dd4](https://github.com/ravensorb/bmad-extensions/commit/f102dd4410fc86ec393d97c3f63638292edb62b8))
* **infra:** widen the flush guard to the two gates its glob could not see ([bd2abf9](https://github.com/ravensorb/bmad-extensions/commit/bd2abf95ac5673c39f88c73557b1014c2e7d8d19))
* **l3io-pm:** free /l3io-help catalog from a menu code l3io-sync already held ([06c7869](https://github.com/ravensorb/bmad-extensions/commit/06c78692fa75f2a6d4c812932f235cd934837d71))


### Performance

* **infra:** cut test:scripts from a quarter-hour to four minutes ([5b3e549](https://github.com/ravensorb/bmad-extensions/commit/5b3e549fcb60b524cde56a610c659d2622e655ac))


### Documentation

* **infra:** make CONTRIBUTING's gate table true, and name the Python suites' real runner ([20b2002](https://github.com/ravensorb/bmad-extensions/commit/20b20022a4c66c3ab11a90dfc1dd80c1136b4d7d))
* **infra:** the --dump-deliveries truncation is loud, not silent ([440c8f9](https://github.com/ravensorb/bmad-extensions/commit/440c8f920ae888ac370e60bada7d5449dff7004c))


### Testing

* **infra:** keep the fixture that produced a failure, and pin the symlink's delete semantics ([2d03356](https://github.com/ravensorb/bmad-extensions/commit/2d0335637b4c21e2fb4987509dfc14cec074617c))
* **infra:** make the check-docs fixture a runnable copy, not just a readable one ([21107c4](https://github.com/ravensorb/bmad-extensions/commit/21107c4b8148ec11c3ec5640fb4bf8e0eace7f65))

## [3.1.8](https://github.com/ravensorb/bmad-extensions/compare/3.1.7...3.1.8) (2026-09-29)


### Fixes

* **l3io-pm:** drop the l3io-pm-setup forwarder, which made the module home a lottery ([67edb10](https://github.com/ravensorb/bmad-extensions/commit/67edb101943f952fd90bc0afcc856a6e643e3aae))

## [3.1.7](https://github.com/ravensorb/bmad-extensions/compare/3.1.6...3.1.7) (2026-09-29)


### Features

* **ci-cd:** lint Python with ruff, and fix everything it found ([c919cb9](https://github.com/ravensorb/bmad-extensions/commit/c919cb9753919d53100682585024b516c90a055c))


### Fixes

* **ci-cd:** lint the repo, not a directory list ([363f3f2](https://github.com/ravensorb/bmad-extensions/commit/363f3f2b8dc8bf5d3a8282992652a3c933afe89d))
* **infra:** smoke-install cleans up after itself, and only after itself ([d2572b8](https://github.com/ravensorb/bmad-extensions/commit/d2572b8c6843a01d24e5615a3316f8e3fbb3387f))
* **l3io-util,infra:** repair Check 20's dead command, and gate the class ([2220df1](https://github.com/ravensorb/bmad-extensions/commit/2220df152ffd2df836eda68cb1c10f0d8c029c11))


### Documentation

* **infra:** add a session handoff note ([0381d2c](https://github.com/ravensorb/bmad-extensions/commit/0381d2c355bfcecb6e23730ae3c79781c0f7c8ee))
* **infra:** name the current KB title, keep the content fallback ([ea5af5f](https://github.com/ravensorb/bmad-extensions/commit/ea5af5fe930ab6c78cf0ae738f07d7ee5c3a15ff))
* **infra:** reclaim four findings the handoff wrongly disclaimed ([309c901](https://github.com/ravensorb/bmad-extensions/commit/309c9015baa2a9cc81ac6d4cc8811dec1f3f1be4))
* **infra:** record the scratchpad deletion and what was kept ([74a632b](https://github.com/ravensorb/bmad-extensions/commit/74a632b091a3ac411b6785272e423020dcf80fb4))
* **infra:** record where the out-of-repo artifacts live ([fe12452](https://github.com/ravensorb/bmad-extensions/commit/fe1245280f18f6aa47daa9b00dced715c9a5b973))
* **infra:** stop the handoff pinning facts git already owns ([68d5c58](https://github.com/ravensorb/bmad-extensions/commit/68d5c580687a5302f5138b08c4e655b19f5c9cf4))
* **infra:** update the handoff for the 3.1.3 verb-first renames ([7daeba9](https://github.com/ravensorb/bmad-extensions/commit/7daeba9dae1e2f9e14bb5cef6963c3b4e003a6d4))
* note the Check 20 repair for 3.1.4 upgraders ([52561ea](https://github.com/ravensorb/bmad-extensions/commit/52561ea69b930746e2d9a5eb393fb1eb5548b254))

## [3.1.6](https://github.com/ravensorb/bmad-extensions/compare/3.1.5...3.1.6) (2026-09-28)


### Maintenance

* **ci:** add scripts/ci-local.mjs thin wrapper for act ([05f1aa4](https://github.com/ravensorb/bmad-extensions/commit/05f1aa4b09c822ae50a68c681012ded880788dd6))

## [3.1.5](https://github.com/ravensorb/bmad-extensions/compare/3.1.4...3.1.5) (2026-09-28)


### Refactoring

* move per-skill tests out of shipped payload ([b9e4aa1](https://github.com/ravensorb/bmad-extensions/commit/b9e4aa12575e13424f1b61eb059d7fce0740dcfd))

## [3.1.4](https://github.com/ravensorb/bmad-extensions/compare/3.1.3...3.1.4) (2026-09-28)


### Fixes

* **l3io-util-doctor:** Check 11 tolerates slug-in-filename convention ([b6343c4](https://github.com/ravensorb/bmad-extensions/commit/b6343c46cf81a95e18767e0fa7b01c0ab233aecf))


### Documentation

* **readme:** remove bmb from user-install module table ([e7ad7e0](https://github.com/ravensorb/bmad-extensions/commit/e7ad7e0c3df5f639657dc808e9acbdfa47df46dd))

## [3.1.3](https://github.com/ravensorb/bmad-extensions/compare/3.1.2...3.1.3) (2026-09-27)


### ⚠ BREAKING CHANGES

* **l3io-doctor:** rename layout-cleanup → clean-layout for verb-first consistency
* **l3io-pm,l3io-util:** verb-first skill names + cross-module discovery mode

### Features

* **ci-cd:** run every Python suite, and gate on bmb's skill scanners ([95bc097](https://github.com/ravensorb/bmad-extensions/commit/95bc09707cfebf00d42abead6cf55a8443191b5b))
* **l3io-pm,l3io-util:** verb-first skill names + cross-module discovery mode ([d3e04cf](https://github.com/ravensorb/bmad-extensions/commit/d3e04cf7d4040b03dadb1dad90b98b1073138133))


### Performance

* **l3io-doctor,infra:** lazy-load doctor help block + trim forwarder payload ([2c1e669](https://github.com/ravensorb/bmad-extensions/commit/2c1e669244e46ac7a5beacde10ff4417d9b27154))


### Refactoring

* **l3io-doctor:** rename layout-cleanup → clean-layout for verb-first consistency ([6da92a4](https://github.com/ravensorb/bmad-extensions/commit/6da92a46b40e2b4723da271ae5183d7a6f29f2f0))


### Documentation

* preserve historical prose in decision-logs and superpowers ([3c9b8a3](https://github.com/ravensorb/bmad-extensions/commit/3c9b8a3bb4be64803e3dfc8a5d633abc060f610c))

## [3.1.2](https://github.com/ravensorb/bmad-extensions/compare/3.1.1...3.1.2) (2026-09-26)


### Fixes

* **infra:** close the six real findings from a bmad-builder validation pass ([1c41f45](https://github.com/ravensorb/bmad-extensions/commit/1c41f450b999431906e2845cb701f95c79beef70))
* **l3io-pm:** grade a missing estimate block amber, not red ([1490ba1](https://github.com/ravensorb/bmad-extensions/commit/1490ba169195aef5ca5c0f2f7569c2ef35225117))
* **l3io-pm:** grade an absent story document amber, not red ([04a0420](https://github.com/ravensorb/bmad-extensions/commit/04a0420472bce57663b110c993b12a0f478b4a85))
* **l3io-pm:** pass the agent contract to the fix re-dispatch too ([56b4ca3](https://github.com/ravensorb/bmad-extensions/commit/56b4ca30eedc1ac06de7dfad7227ab876a34bdd9))
* **l3io-pm:** rebuild calibration in closure order, or refuse ([1a87d6e](https://github.com/ravensorb/bmad-extensions/commit/1a87d6e282b9c62e4efd321118a9836daa4ddb2d))
* **l3io-pm:** scan ADRs whose filename carries the ADR- prefix ([949a3d5](https://github.com/ravensorb/bmad-extensions/commit/949a3d551431fece1f09e4886ede15cef90a72f4))

## [3.1.1](https://github.com/ravensorb/bmad-extensions/compare/3.1.0...3.1.1) (2026-09-26)


### Features

* **infra:** checks 28 and 29 close two holes CLAUDE.md documented in prose ([f439999](https://github.com/ravensorb/bmad-extensions/commit/f4399996ce5e8abcb4b2ffde5dba7c75f9883982))
* **l3io-arch:** author the docker, powershell and shell standards overlays ([0d95a52](https://github.com/ravensorb/bmad-extensions/commit/0d95a5209d2fd2d144206dd5ac8e0603d43d7342))
* **l3io-pm,l3io-util:** set-depends-on, so migrations stop dropping dependencies ([19a476d](https://github.com/ravensorb/bmad-extensions/commit/19a476dba4658ea50010b60fddd1750fdc19c1e4))
* **l3io-pm:** epic-aware legacy migration, a deferred resolution, and import-actual ([0e17dab](https://github.com/ravensorb/bmad-extensions/commit/0e17dab11348e205524052eb1a7f917e2274e71a))
* **l3io-util:** typed writers for estimate and actual — migrations lose nothing ([2265841](https://github.com/ravensorb/bmad-extensions/commit/2265841cee5c9195ce0d22ab5e7a05bbd3536e4c))


### Fixes

* **infra:** the doctor keyword set comes from the routing table, not any table ([55ba682](https://github.com/ravensorb/bmad-extensions/commit/55ba68278c9d05e432282cd86595bef7b8f58990))
* **l3io-pm:** normalize-status refuses when deferred and backlog coexist ([457cfcc](https://github.com/ravensorb/bmad-extensions/commit/457cfcce978a046c228bda5ea7cf49b8bde3a2a9))


### Refactoring

* **l3io-arch:** scope the PowerShell standard to the major, not an LTS minor ([b3fc38c](https://github.com/ravensorb/bmad-extensions/commit/b3fc38cc2827bef2c1adb9bdb18076e03ba7ddab))
* **l3io-pm:** remove max_fix_iterations_non_code, the one removable knob ([381b052](https://github.com/ravensorb/bmad-extensions/commit/381b052f664a797bae2a2a4742473be57b6bfefd))


### Documentation

* full assessment of outstanding work, measured against the tree ([0ae84e9](https://github.com/ravensorb/bmad-extensions/commit/0ae84e9c64f47586bfd28fafccbe7c1db7f75764))
* record the evidence for the epic-aware issue migration ([155b00d](https://github.com/ravensorb/bmad-extensions/commit/155b00dff552ed2f1e1c1e889fb52111f8c7afde))

## [3.1.0](https://github.com/ravensorb/bmad-extensions/compare/3.0.2...3.1.0) (2026-09-26)


### Features

* **l3io-pm,l3io-util:** structured issue source, derived rather than parsed ([efca47d](https://github.com/ravensorb/bmad-extensions/commit/efca47d7148bea7fd834e738e195288540019a6a))
* **l3io-util:** close the six open gaps from the doctor capability analysis ([e696380](https://github.com/ravensorb/bmad-extensions/commit/e6963805b2d1e255c89eb8337274144215dc44ef))


### Documentation

* **l3io-util:** mark the doctor gap analysis closed, all ten resolved ([972a733](https://github.com/ravensorb/bmad-extensions/commit/972a7335a58160c2b454c6eec7de7f07b6a3ce87))

## [3.0.2](https://github.com/ravensorb/bmad-extensions/compare/3.0.1...3.0.2) (2026-09-26)


### Features

* **ci-cd:** check:lock refuses release and blocks CI on package-lock drift ([55d770b](https://github.com/ravensorb/bmad-extensions/commit/55d770bffcb428558d64583cf769e1aa94e6d49c))
* **infra:** check 27 fails a doc that enumerates a flag's choices incompletely ([30575d0](https://github.com/ravensorb/bmad-extensions/commit/30575d0276d196644c234700edc288c5c9bc199e))
* **infra:** Stage 4 — check 4 required-flags-per-status extension ([a5c4fbb](https://github.com/ravensorb/bmad-extensions/commit/a5c4fbb52b02258ed5d44e359cb00da23649f5d9)), closes [#4](https://github.com/ravensorb/bmad-extensions/issues/4)
* **l3io-pm,l3io-util:** detect bmad-loop and inform, no integration ([2e77e53](https://github.com/ravensorb/bmad-extensions/commit/2e77e53eb50d7b5001889e965700982218c6edf7))
* **l3io-pm:** close the two blocked-status revisit-if-warranted follow-ups ([9cf4d9e](https://github.com/ravensorb/bmad-extensions/commit/9cf4d9ee51155ee1aeb7540e0fc88340946e5cc3))
* **l3io-pm:** Stage 1 — story-lifecycle blocked status enum + transitions ([760ef93](https://github.com/ravensorb/bmad-extensions/commit/760ef9330513752f2dd5c0ebc811e1698fccdfbb))
* **l3io-pm:** Stage 2 — calibration exclusion + blocks_seen counter ([4cf6685](https://github.com/ravensorb/bmad-extensions/commit/4cf66859f83f2fa13cfc38340c83cc401c434417))
* **l3io-pm:** Stage 3 — closure BLOCKED: diagnostic + report/show rendering ([811c171](https://github.com/ravensorb/bmad-extensions/commit/811c1711ce39f33f7263ee098827a41ac23a2256))


### Fixes

* **l3io-pm:** a legacy `deferred` issue status is migratable, not just reportable ([5e11179](https://github.com/ravensorb/bmad-extensions/commit/5e111798e8848c793fcdf41eeed046a9232080d9))
* **l3io-util,infra:** layout-cleanup follows a tree's convention instead of imposing one ([74a42f7](https://github.com/ravensorb/bmad-extensions/commit/74a42f702db2b6be56fb6c5c4b7630dee4ff442e))
* **l3io-util:** audit-backlog resolves the source shapes real backlogs contain ([882add0](https://github.com/ravensorb/bmad-extensions/commit/882add0531b4504748186fa9e17cccc40a71c925))
* **l3io-util:** migrate-adrs no longer renumbers an already-migrated ADR ([4174c95](https://github.com/ravensorb/bmad-extensions/commit/4174c95ca33bb03e067a7f1cf8124969056d8069))
* **l3io-util:** the health check stops recommending the run that harms you ([160bb0d](https://github.com/ravensorb/bmad-extensions/commit/160bb0d9472c19274a50f9b81f4bf05a6c5fe3de))


### Documentation

* amend blocked design §5 — total_blocked_hours scan scoping ([17c65b6](https://github.com/ravensorb/bmad-extensions/commit/17c65b67091a4c004751efe94e747e03b73a41f6))
* design pass for story-lifecycle blocked status ([d939d06](https://github.com/ravensorb/bmad-extensions/commit/d939d06b16180be4b89140286fdebfce033f0b10))
* document the four fixes for users, not just in the step files ([e8b543d](https://github.com/ravensorb/bmad-extensions/commit/e8b543d417c162d8bf2a38cb498591df5e219ea3))
* **l3io-pm:** closure prose — BLOCKED: wins over FAILED: when both apply ([18b2f4e](https://github.com/ravensorb/bmad-extensions/commit/18b2f4e5a7672f11381d5962b9667cfce1b7b774))
* **l3io-pm:** design for structured issue source fields ([1e71d26](https://github.com/ravensorb/bmad-extensions/commit/1e71d2689184135b0b1953582298c696ed63c8b0))


### Maintenance

* **ci-cd:** regenerate package-lock.json to sync with package.json ([10f70cb](https://github.com/ravensorb/bmad-extensions/commit/10f70cb38f453caf99568e9ebe669b530068fdd2))

## [3.0.1](https://github.com/ravensorb/bmad-extensions/compare/3.0.0...3.0.1) (2026-09-25)


### Features

* **l3io-pm,l3io-util:** list-epics and list-stories read-only enumerators ([1c25007](https://github.com/ravensorb/bmad-extensions/commit/1c25007a81755fd01fc1165bd2a20d426ccbd915))
* **l3io-util:** additive bootstrap on partial sharded state ([d38f879](https://github.com/ravensorb/bmad-extensions/commit/d38f8798d4f882949232677c6ace011317f69ef1))
* **l3io-util:** migration extras carry-through with skip-and-log ([e2dcb65](https://github.com/ravensorb/bmad-extensions/commit/e2dcb652b09b7bc9212a8d951571a3e09712d83d))


### Refactoring

* **infra:** check 26 exemption reads a body marker, not a filename ([126c26c](https://github.com/ravensorb/bmad-extensions/commit/126c26c63500cce8c33119fef1074c3f399e2910))


### Documentation

* sync CLAUDE.md, upgrading.md and l3io-util reference for 3.0.1 ([9ad27f8](https://github.com/ravensorb/bmad-extensions/commit/9ad27f8765d260a6a479334545fce722207bbb4f))


### Testing

* **l3io-util:** pin partial-write survival with a real multi-record fixture ([bd08f93](https://github.com/ravensorb/bmad-extensions/commit/bd08f93cd4bed21ca7ad957e697f2e782ed9e7d3))

## [3.0.0](https://github.com/ravensorb/bmad-extensions/compare/2.5.2...3.0.0) (2026-09-24)


### ⚠ BREAKING CHANGES

* **infra:** one module.yaml per module, under assets/
* **l3io-util:** /l3io-util-cleanup no longer exists. Use /l3io-doctor.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Signed-off-by: Shawn Anderson <sanderson@eye-catcher.com>

### Features

* **infra:** add check-docs check 20, shared-files-table ([c5ff1ab](https://github.com/ravensorb/bmad-extensions/commit/c5ff1abc5c362bed89b2d7e4872c31bc96024ffa))
* **infra:** add check:module, the guard Phase 2's invariant needs ([6aa43a6](https://github.com/ravensorb/bmad-extensions/commit/6aa43a6f3882f4d84977e7455792f2c1d7e4b840))
* **infra:** add merge-config.py and merge-help-csv.py ([188f201](https://github.com/ravensorb/bmad-extensions/commit/188f201909e7dcfb44944acfb666d5228d68ddc3))
* **infra:** check 17 fails when a directive prefers a deprecated skill ([3a8bff9](https://github.com/ravensorb/bmad-extensions/commit/3a8bff9494121fa3b2df15fbc5f620d0e964d162))
* **infra:** check 26 keeps state-path assembly in the resolver section ([760c2f4](https://github.com/ravensorb/bmad-extensions/commit/760c2f4c8aff064fe7ca6f22ea4957114d77c422))
* **infra:** check:docs guards /l3io-doctor mode keywords ([1761828](https://github.com/ravensorb/bmad-extensions/commit/17618282a69626ed177901d92f7fc9b29b4a902b))
* **infra:** check:module rule 9 — every documented mode keyword is registered or excluded ([5703dfc](https://github.com/ravensorb/bmad-extensions/commit/5703dfca12a123280083e86cf243ac249598051c))
* **infra:** derive the skill and module counts too ([59ce0ef](https://github.com/ravensorb/bmad-extensions/commit/59ce0ef02092bff3e89515f4a7dd0cbc34f027e6))
* **infra:** guard the installer's silent fallthrough to a synthesized catalog ([7ba1467](https://github.com/ravensorb/bmad-extensions/commit/7ba1467aed557129db82108bbad4a116c2480c16))
* **infra:** guard the README layout block and pm-status invocations in skills/ ([7d92890](https://github.com/ravensorb/bmad-extensions/commit/7d92890e30b991758f62e49b826e5ebffb40791f))
* **infra:** pin the BMad conformance baseline and smoke-test the install ([780a95c](https://github.com/ravensorb/bmad-extensions/commit/780a95c6965f7e7478943961bc665b091087a10d))
* **l3io-arch:** register l3io-arch-review's three modes as three rows ([6a60424](https://github.com/ravensorb/bmad-extensions/commit/6a6042431ba53d4109b1cba6b6cf456d13f2efd0))
* **l3io-pm:** add l3io-setup, the module's setup skill ([b7c0b1f](https://github.com/ravensorb/bmad-extensions/commit/b7c0b1f4e26e469dcd091178f28d0e40a32b00a3))
* **l3io-pm:** ensure_node_path -- the one function that creates a node dir ([ae4f63e](https://github.com/ravensorb/bmad-extensions/commit/ae4f63e5b2a070179cced2b10337486f3fa884d8))
* **l3io-pm:** import-node creates a state node from a migration record ([af63d8b](https://github.com/ravensorb/bmad-extensions/commit/af63d8b52b51f6da5791014a439ecc915a227fbd))
* **l3io-pm:** mention the setup skill at most once per session ([92e9b2e](https://github.com/ravensorb/bmad-extensions/commit/92e9b2e140214a4250343bc36eb58bb4fd62c618))
* **l3io-pm:** register l3io-help's progress and list plan modes ([f56b61d](https://github.com/ravensorb/bmad-extensions/commit/f56b61d9ef8a75d2561f571b59253a402df5f8e4))
* **l3io-pm:** warn at activation when l3io-doctor is missing ([d8f0f43](https://github.com/ravensorb/bmad-extensions/commit/d8f0f43df0fdc8487b4f8123a31e0862a712343e))
* **l3io-sec:** check:module rule 10 — the agent roster and its skill's [agent] block agree ([63066b2](https://github.com/ravensorb/bmad-extensions/commit/63066b20032d74b2597b2a080b123b6bd72cae03))
* **l3io-util,l3io-pm:** pm-help checks pm-status.py freshness via new doctor mode ([f94af3e](https://github.com/ravensorb/bmad-extensions/commit/f94af3e247a6b4fac89ead167252f85da5cfbde9))
* **l3io-util:** add a deprecated dependency status distinct from removed ([2c5adda](https://github.com/ravensorb/bmad-extensions/commit/2c5adda2411fddc7980e9866343f59ea144eb29a))
* **l3io-util:** add per-epic fixture files (force-add past _bmad/ gitignore) ([91b43bd](https://github.com/ravensorb/bmad-extensions/commit/91b43bd65eabc5052b5ce47365befb8cf85f93fe))
* **l3io-util:** add the overlay mode, owner of the BMad customization layer ([5d61c2c](https://github.com/ravensorb/bmad-extensions/commit/5d61c2c50b52e61876ae1746a1d337102babeb28))
* **l3io-util:** derive dependency truth from BMad's own manifest ([5ee4f72](https://github.com/ravensorb/bmad-extensions/commit/5ee4f7217128ef4612206804dc860bbcaa056aab))
* **l3io-util:** derive records from story artifacts, sprints inferred ([f0c8927](https://github.com/ravensorb/bmad-extensions/commit/f0c8927acd0bb5ceaf3b1b21a5c64cff666eb106))
* **l3io-util:** detect a project holding both state layouts ([b55f464](https://github.com/ravensorb/bmad-extensions/commit/b55f4643cadbe84fdbd2f50ebef0038546f19755))
* **l3io-util:** detect-layout classifies a flat status file by schema ([41b122c](https://github.com/ravensorb/bmad-extensions/commit/41b122c9b172765f3cd841d28f6b886a4269d75b))
* **l3io-util:** migration engine, read-only half ([56d16ff](https://github.com/ravensorb/bmad-extensions/commit/56d16ff8cf1ea797604ff204abbaa2664a7145b3))
* **l3io-util:** reader for base BMad's development_status mapping ([f6d297c](https://github.com/ravensorb/bmad-extensions/commit/f6d297cdc7793fe6200baba2d93d52dde48ca276))
* **l3io-util:** reader for the legacy flat epics: list ([cc50649](https://github.com/ravensorb/bmad-extensions/commit/cc5064927bb71513bdf4b06646e91de4f87c5ff6))
* **l3io-util:** reader for the legacy per-epic _bmad/state layout ([38859fc](https://github.com/ravensorb/bmad-extensions/commit/38859fcc2fe9b3f42a7f8211ba797e7b45524bba))
* **l3io-util:** reader for the split three-file status layout ([425e3a7](https://github.com/ravensorb/bmad-extensions/commit/425e3a756f08ad288e8d03cb821e49d04ea1b7a0))
* **l3io-util:** register the doctor's three entry points and record the exclusions ([dcf0173](https://github.com/ravensorb/bmad-extensions/commit/dcf0173cd63d65278fad4b75faf781958b8598f6))
* **l3io-util:** remove the deprecated l3io-util-cleanup forwarder ([217ba7d](https://github.com/ravensorb/bmad-extensions/commit/217ba7deff1f0cfb03b02c156ffa3b38ff750ede))
* **l3io-util:** stats surfaces the clear-lock remedy, watch hint, and dwell note ([6c4779c](https://github.com/ravensorb/bmad-extensions/commit/6c4779c09b52f5d14677fe30c51581543067797a))
* **l3io-util:** the gate, the write, and verification against the plan ([d0707f2](https://github.com/ravensorb/bmad-extensions/commit/d0707f2159b99eb572ff1968eadd1b03f0435f70))
* **l3io-util:** the normalised record every doctor reader emits ([0b15dd6](https://github.com/ravensorb/bmad-extensions/commit/0b15dd687decf2745824537d1afa0b52964b68ca))


### Fixes

* **ci-cd:** consolidate GitHub Actions on current, act-verified versions ([c568b72](https://github.com/ravensorb/bmad-extensions/commit/c568b7294f895bcd89df283f52d07d511c52d172))
* **ci:** close the command-chain hole in check 17's uv-run exemption (F-1) ([31cafeb](https://github.com/ravensorb/bmad-extensions/commit/31cafebf3bd63f9dd1e22f85821a081425659882))
* **ci:** close two new holes in check 17's F-1 fix, and its pre-existing cheap exit (N-1, N-2, N-3) ([513c927](https://github.com/ravensorb/bmad-extensions/commit/513c92738779a152c4f1a4bcd1d33087bb9c0639))
* **ci:** constrain check 17's token skip to flag shapes so prose stops tripping it (R-1) ([d8958a6](https://github.com/ravensorb/bmad-extensions/commit/d8958a6f1861a78de19ee6266c3613df79712321))
* **ci:** stop provisioning pm-status.py tests via ambient pip, add check:module gate ([af9770c](https://github.com/ravensorb/bmad-extensions/commit/af9770c2f8e68854812c46ebd27cc1954735635f))
* **ci:** widen check 17's python3 predicate past interpreter flags and minor versions (M-1) ([7d465c6](https://github.com/ravensorb/bmad-extensions/commit/7d465c6712e07cc0386f81211d1ab5486426621d))
* **infra:** add check 19 to guard the check count, per review round 1 ([70c5cbe](https://github.com/ravensorb/bmad-extensions/commit/70c5cbe71eb670c5c022117211ccee75175ab136))
* **infra:** check 4 no longer misjudges doctor keywords or other tools' subcommands ([03bc390](https://github.com/ravensorb/bmad-extensions/commit/03bc3909b4233cef3873239c1503898fac41406c))
* **infra:** close eleven of checks 4 and 17's KNOWN GAPS, and re-measure the rest ([4b0fdba](https://github.com/ravensorb/bmad-extensions/commit/4b0fdbafc0006b2849674724d466d61fc113d4b3))
* **infra:** close remaining setup-routing drift and guard against orphaned payload ([0c9bc21](https://github.com/ravensorb/bmad-extensions/commit/0c9bc2177b141ce49368514bc831e2696f4317ab))
* **infra:** close Task 7 fix-round-1 findings — renumbering, module-setup path, version guard ([79b3fe5](https://github.com/ravensorb/bmad-extensions/commit/79b3fe5d8b2872ec621aeac31a9ccfcf39e7018b))
* **infra:** derive check 22's "on disk" from git, not the filesystem ([0d7e1be](https://github.com/ravensorb/bmad-extensions/commit/0d7e1bea11569a21731845ebb55d9151ebd56829))
* **infra:** derive check 4's completeness set, and document the 12 subcommands it found ([dd624ca](https://github.com/ravensorb/bmad-extensions/commit/dd624ca1bf468e5e5d05d53bf045d597112e7e97))
* **infra:** drop two module-help flags that are implemented nowhere ([ce4a5fd](https://github.com/ravensorb/bmad-extensions/commit/ce4a5fda24e236485a3edd52026f80f2ade01a21))
* **infra:** extend check 17 to the live docs, and fix the 17 python3 invocations it found ([88c9552](https://github.com/ravensorb/bmad-extensions/commit/88c955247daa3171e5a45b0d18a0b736e1e09e20))
* **infra:** filter allSkillDirs to directories, not just l3io- names (F-8) ([99371d9](https://github.com/ravensorb/bmad-extensions/commit/99371d96e8703c32cadf83ef621ce64b65150922))
* **infra:** invoke PEP-723 helpers with uv, as BMad does ([db983ef](https://github.com/ravensorb/bmad-extensions/commit/db983efff5495fcdd89f809863726528e91e8a41))
* **infra:** make smoke:install able to pass again, and guard overlay's cp ([2daace2](https://github.com/ravensorb/bmad-extensions/commit/2daace20c667597684706650090ec49caf37da64))
* **infra:** make the module-contract smoke check state-derived ([ee41084](https://github.com/ravensorb/bmad-extensions/commit/ee41084d5ae3fc46b7b62c23b3f894a6391e6822))
* **infra:** narrow check 26 regex to require state-context tokens ([b418a13](https://github.com/ravensorb/bmad-extensions/commit/b418a13239370c3b3b0dae1bfc12ced5a4448390))
* **infra:** one action and phase vocabulary, _meta rows, and the documented relationships ([260f3b0](https://github.com/ravensorb/bmad-extensions/commit/260f3b031ffeb0edb4efa2a54438bbaa63d4b2a1))
* **infra:** pin check 17's python3 arity model, and correct four claims about it ([988b5c8](https://github.com/ravensorb/bmad-extensions/commit/988b5c87e7f1ecb41f9c9b1149e588d11ddc3db0))
* **infra:** qualify the bare-binding anchor on code formatting, and finish the migrate-state set ([c4f488d](https://github.com/ravensorb/bmad-extensions/commit/c4f488dddce8f8704e1bdf987951cfe1d640b3d2))
* **infra:** read a `\`-continued invocation whole, and broaden smoke's negative twin ([150a6fe](https://github.com/ravensorb/bmad-extensions/commit/150a6fefb2a43f5f1b87e1a51db8c5b377298ba0))
* **infra:** rebuild check 17 on a YAML and a shell parser, and check 21 in process ([bf7dcb3](https://github.com/ravensorb/bmad-extensions/commit/bf7dcb36b7ccdb7863d63aa6e70e83605de19450))
* **infra:** smoke:install judges validate-module.py's findings, not its verdict ([3da080d](https://github.com/ravensorb/bmad-extensions/commit/3da080db2353d39ca015614f49aee1a8eec7abc6))
* **infra:** walk docs/ recursively, so the ADRs are inside the checks at all ([4add491](https://github.com/ravensorb/bmad-extensions/commit/4add4913b85ca8a4988892beea1e53033cffc2b5))
* **infra:** widen check 17's preference detection past binding verbs ([4169034](https://github.com/ravensorb/bmad-extensions/commit/4169034052db3b4401d05d98bfb556eedd3abeb7))
* **l3io-arch:** correct the arch-review row's args, output location and phase ([1e751c2](https://github.com/ravensorb/bmad-extensions/commit/1e751c25babe3afc5ebc88e1648d05ce7f1a1ba5))
* **l3io-pm:** adr-reserve refuses rather than guessing when it cannot scan the ADR home ([126ae9a](https://github.com/ravensorb/bmad-extensions/commit/126ae9adf97d196198e0f57299f45e411d73a1f2))
* **l3io-pm:** check 21 also validates description, per Task 11A re-review ([0c05008](https://github.com/ravensorb/bmad-extensions/commit/0c0500847bd6335aafc62d2715dd675e8d9eaeff))
* **l3io-pm:** correct Estimate's output location, Plan's required flag and the APM code ([b44be3e](https://github.com/ravensorb/bmad-extensions/commit/b44be3e19531aac8c34a33c4967ca2e2ec692666))
* **l3io-pm:** gate the setup pointer on absence and give notice failures a distinct exit code ([b47d249](https://github.com/ravensorb/bmad-extensions/commit/b47d24958a42fbf5496ec4e8076eb2619def54f6))
* **l3io-pm:** inline unreachable section-5 content in pm-help modes, fix Repo Layout drift ([ff5e134](https://github.com/ravensorb/bmad-extensions/commit/ff5e134c48c5b27af074e0258f0c921969724a9c))
* **l3io-pm:** l3io-execute is single-action, so its ref carries no action ([738d39b](https://github.com/ravensorb/bmad-extensions/commit/738d39b9bd38911027ec6ec5cf7933e796a363dc))
* **l3io-pm:** quote l3io-sync's frontmatter, guard the class in check:docs ([1214fe1](https://github.com/ravensorb/bmad-extensions/commit/1214fe14dac92e8abcec6c1a3915692d3424da36))
* **l3io-pm:** re-scope the setup pointer to once-per-project, not once-per-session ([0ebe110](https://github.com/ravensorb/bmad-extensions/commit/0ebe1101fd0d90b8e520a9f2e8ed51b848939237))
* **l3io-sec:** resolve First Breath's config the documented way, not from a file that does not exist ([2f372b0](https://github.com/ravensorb/bmad-extensions/commit/2f372b02b3b200c7a839b217f1fea9616919ffc2))
* **l3io-util:** bootstrap-state writes an all-done sprint as done, stated once ([cc96021](https://github.com/ravensorb/bmad-extensions/commit/cc96021f9e64199ccf168d2e3a2ac178952b55c1))
* **l3io-util:** fold the layout-collision check into 2b, not a sibling ([9b84c3a](https://github.com/ravensorb/bmad-extensions/commit/9b84c3ae9e9902ac47a0b31aa2180bc8569fea6a))
* **l3io-util:** renumber the last stale check-17 references in bmad-dependencies.json ([8e3d756](https://github.com/ravensorb/bmad-extensions/commit/8e3d7569d7e1d35707f44bb25b023db019aeb26f))
* **l3io-util:** ship status-files.md to l3io-doctor, which pointed at it in six places ([180c9ba](https://github.com/ravensorb/bmad-extensions/commit/180c9ba26f0f6c404e208fc7587d979113430d4c))
* **l3io-util:** sort-status pointed at a mode file that no longer exists ([a91b429](https://github.com/ravensorb/bmad-extensions/commit/a91b429acb76c9ffda431d5766e7b7eb4273231a))
* **l3io-util:** stats BLOCKs on a repointed implementation_artifacts orphan ([dd1c4c7](https://github.com/ravensorb/bmad-extensions/commit/dd1c4c7657fd4bf06bdcfea6f71ccb16a8dedaa4))
* **l3io-util:** stats BLOCKs on multiple state layouts, matching Check 2b ([38d52d7](https://github.com/ravensorb/bmad-extensions/commit/38d52d71e89ac73e58dac507c4361454f64a31d1))
* **l3io-util:** sweep the .v1 calibration backup where pm-status.py actually writes it ([5df7f0a](https://github.com/ravensorb/bmad-extensions/commit/5df7f0a9560da632cc785e57bcba3dfcafd5369f))
* **l3io-util:** three dependencies are deprecated, not removed ([0150144](https://github.com/ravensorb/bmad-extensions/commit/015014459faa3fc9de84d538bee99bc4b5081682))
* **l3io-util:** triage no longer refuses the case Check 13 flags it for ([b969b28](https://github.com/ravensorb/bmad-extensions/commit/b969b28defb3e14b74fa7a9007cb59dbc9f237ee))
* **l3io-util:** update-ai-rules creates the running AI's file, never another's ([abcc760](https://github.com/ravensorb/bmad-extensions/commit/abcc760cc54c738d537598d1e4eab4efcbfec6b1))
* **l3io:** put module.yaml where BMad's installer actually discovers it ([1701734](https://github.com/ravensorb/bmad-extensions/commit/1701734ca73b9868fdc1fe1f0df874ac0b76ef9e))
* **l3io:** remove phantom module-help.csv rows, guard the class in check:module (F-4) ([f766eb7](https://github.com/ravensorb/bmad-extensions/commit/f766eb73b414a8823fce4ff0eb4b56c661ddebb7))


### Refactoring

* **infra:** check:module parses module.yaml and module-help.csv with libraries ([7c9254e](https://github.com/ravensorb/bmad-extensions/commit/7c9254e567e746ec3675f5dc3b60404d14ee69cb))
* **infra:** exempt description-only prose from check 26; suppress 5 read-only state probes ([1586555](https://github.com/ravensorb/bmad-extensions/commit/158655562214d2500c0e66d0fed4831918f0c15d))
* **infra:** exempt SKILL.md, test files, python comments, and docstrings from check 26 ([b0d5277](https://github.com/ravensorb/bmad-extensions/commit/b0d527747c0a920f1343c1a7b587badd78b34a5c))
* **infra:** one module.yaml per module, under assets/ ([ff1632b](https://github.com/ravensorb/bmad-extensions/commit/ff1632b6e606510dea66d28260cbc04318c8d57c))
* **infra:** sync setup payload to module homes only ([ada16fd](https://github.com/ravensorb/bmad-extensions/commit/ada16fdbe7e35ac068e0ede2f53226ad7f68f1a2))
* **l3io-pm:** pm-help progress forwards to doctor stats ([79595f5](https://github.com/ravensorb/bmad-extensions/commit/79595f50acefaadf4c50814d3c52650a02ea4d82))
* **l3io-pm:** ship one pm-status.py payload per module ([51fb4bb](https://github.com/ravensorb/bmad-extensions/commit/51fb4bb35fa8f59b5674114221a8f94efba308e9))
* **l3io-pm:** split l3io-help into a router and steps/ ([e2fb221](https://github.com/ravensorb/bmad-extensions/commit/e2fb221c1750f637cb1faf465530c2ff48577abe))
* **l3io-util:** bootstrap-state is prose around the engine ([f1cf28c](https://github.com/ravensorb/bmad-extensions/commit/f1cf28cef264c5cebb3323baef9f3294b4e25f05))
* **l3io-util:** demote the overlay doctor mode to a specification ([c5a8966](https://github.com/ravensorb/bmad-extensions/commit/c5a896604cece3a1165e8436013c9eed37afdfa3))
* **l3io-util:** fold rename-active and rename-epic-dirs into health-check ([e18b4e4](https://github.com/ravensorb/bmad-extensions/commit/e18b4e40c71f2af298bd6b14ee54fe42cecf705e))
* **l3io-util:** fold the backlog doctor mode into stats ([88fb918](https://github.com/ravensorb/bmad-extensions/commit/88fb918c7df57c239d1baf9e8db8b38021f784e8))
* **l3io-util:** migrate-state is prose around the engine ([63d7ec9](https://github.com/ravensorb/bmad-extensions/commit/63d7ec945d7df57681e0827d5b6509a1901afaf0))
* **l3io-util:** remove the normalize doctor mode ([26b0302](https://github.com/ravensorb/bmad-extensions/commit/26b0302ecacffb1e3a64416e71406b229f63f1ac))


### Documentation

* correct eleven verified claims across the root docs and references ([c12d2fc](https://github.com/ravensorb/bmad-extensions/commit/c12d2fc3270bda4ab531a452ab25e969b88938b1))
* correct follow-up marker count from 5 to 2 ([ff6bb21](https://github.com/ravensorb/bmad-extensions/commit/ff6bb211b58685ed6b6731061d3cc4edf14ba769))
* **infra:** resolve every cross-skill pointer in the shared files, and gate the class ([57c7463](https://github.com/ravensorb/bmad-extensions/commit/57c74634755054fb50a699ee8ce226391214ae69))
* **infra:** the gates are not dependency-free, and say where the install goes ([d9867a0](https://github.com/ravensorb/bmad-extensions/commit/d9867a053fa97ec5978e8f65cd59a54af005dbea))
* **l3io-pm,infra:** declare l3io-util as a required intra-package module dependency ([4e9f229](https://github.com/ravensorb/bmad-extensions/commit/4e9f2292eac41461361c29e9d1e0a8e3467be852))
* **l3io-pm:** cross-link the inlined stale-lock/pm-status duplicates ([07452be](https://github.com/ravensorb/bmad-extensions/commit/07452be49c22c99b041ddce264259b826d419a94))
* **l3io-util:** add l3io-doctor capability gap analysis ([a07af25](https://github.com/ravensorb/bmad-extensions/commit/a07af254f37900c77eb20aab093a49ac47b62f36))
* **l3io-util:** bootstrap-state is a second hand-rolled node writer ([e42fff6](https://github.com/ravensorb/bmad-extensions/commit/e42fff6b70e4be0eed7b42d4e33a1346654d707a))
* **l3io-util:** design for the l3io-doctor redesign ([b6ad5d9](https://github.com/ravensorb/bmad-extensions/commit/b6ad5d9da56aba2c0412d5a9d567640e857c45bd))
* **l3io-util:** implementation plan for the doctor redesign ([d62d74e](https://github.com/ravensorb/bmad-extensions/commit/d62d74e99d5f9a824591d25c9c74e890f4b67d1b))
* **l3io-util:** plan the doctor cleanup ahead of help registration ([567c017](https://github.com/ravensorb/bmad-extensions/commit/567c017e5185e5483deb8d473a74bdcd964ed3ba))
* **l3io-util:** re-derive Task 5's register set after Phase 0 ([5944cc3](https://github.com/ravensorb/bmad-extensions/commit/5944cc3d2815492a84b674e07f8d4d3d9db2b696))
* **l3io-util:** tidy the stats alias list in the doctor's mode overview ([fd66dfe](https://github.com/ravensorb/bmad-extensions/commit/fd66dfeb4b5c6ab77a4a7981cd052c421593cb0e))
* **l3io:** add Task 0B — derive the skill and module counts ([2b0335f](https://github.com/ravensorb/bmad-extensions/commit/2b0335f2926fdf876b9798c554a2005fef29d8f1))
* **l3io:** add Task 17 — replace hand-rolled parsers with libraries ([3bdcda9](https://github.com/ravensorb/bmad-extensions/commit/3bdcda925541c813cd43e33b1bf46f0be65d30ce))
* **l3io:** add Task 8A — guard the Shared Files table ([ce3d2be](https://github.com/ravensorb/bmad-extensions/commit/ce3d2be9e4ba274841920b5cd2092376f34549ec))
* **l3io:** correct an unreachable Phase 1 exit criterion ([1637c8a](https://github.com/ravensorb/bmad-extensions/commit/1637c8a076be545c8962578c50c467f0e67fdbd4))
* **l3io:** correct module-setup and skill-count claims after l3io-setup ([1dabc33](https://github.com/ravensorb/bmad-extensions/commit/1dabc332bd51c6c612ab8a28ba57b592bd577a02))
* **l3io:** correct Task 0's scope and fix two bugs found by running its own code ([b55c196](https://github.com/ravensorb/bmad-extensions/commit/b55c1965b89d666d3ffb6dd747e014b151765bf8))
* **l3io:** correct the spec's root cause and install behaviour ([30a5fc3](https://github.com/ravensorb/bmad-extensions/commit/30a5fc3ad3f7ff7f53913f197939c19feb6cd902))
* **l3io:** design l3io as a customization layer over BMad ([81b0bf1](https://github.com/ravensorb/bmad-extensions/commit/81b0bf159f99347fbf10fef8a9170c0f0b91111e))
* **l3io:** finish correcting the stale setup-step claim (F-2, F-3) ([7edcb63](https://github.com/ravensorb/bmad-extensions/commit/7edcb633a4d57aa8b6312fb8aab19ef0b499a515))
* **l3io:** fix Task 0's edit set and drop a task solving a non-problem ([e08f8ab](https://github.com/ravensorb/bmad-extensions/commit/e08f8abe3c22ea9057708adfa761be0bf11669c4))
* **l3io:** fix three more assumptions the plan was standing on ([9f25512](https://github.com/ravensorb/bmad-extensions/commit/9f25512c0739c8d95785f40c1df1d571b2f578a4))
* **l3io:** full pre-development verification sweep ([821b472](https://github.com/ravensorb/bmad-extensions/commit/821b47279a5140a7a9814b76bd5326737546405b))
* **l3io:** plan Phases 1-2 of the customization-layer design ([8a2d658](https://github.com/ravensorb/bmad-extensions/commit/8a2d6582eff67669a2244cae7be6c282e2d30cf2))
* **l3io:** record ADR-0008, the module packaging shape ([cc6612a](https://github.com/ravensorb/bmad-extensions/commit/cc6612a46741fe14b54b9711dad2c0eaba1939a3))
* **l3io:** revise the plan after auditing it against recorded decisions ([ca98d7e](https://github.com/ravensorb/bmad-extensions/commit/ca98d7edce0f732dc80f3dd65f67145b81b1f5ab))
* **l3io:** use uv as BMad does, ship one pm-status.py per module, prove every task ([68babe9](https://github.com/ravensorb/bmad-extensions/commit/68babe96755842cdebeac3284e65280b2ee737c9))
* point at where the artifact schema actually lives ([4d305da](https://github.com/ravensorb/bmad-extensions/commit/4d305da2b2fc58f029395607cf7f38f7170ecd96))
* README no longer advertises the removed `overlay` doctor keyword ([4bf6104](https://github.com/ravensorb/bmad-extensions/commit/4bf61041ccdbd48e4e49081c1047a21966f1950a))
* record the module.yaml discovery contract read from project-root.js ([971a517](https://github.com/ravensorb/bmad-extensions/commit/971a517aa375755af67e8ab36b7dc507455b1222))
* redact machine paths and dead scratch pointers ([b418896](https://github.com/ravensorb/bmad-extensions/commit/b4188967d2f013f1a40b89f25628b0f157d1e83c))
* sync user-facing docs with the l3io-util-required + check-pm-status changes ([30f9173](https://github.com/ravensorb/bmad-extensions/commit/30f91738e207e990ec3767393a6e2d07a735224a))
* the doctor's migrations are an engine, not prose ([12cc9cd](https://github.com/ravensorb/bmad-extensions/commit/12cc9cd540a04f44ffd2fdc2f78a4bbad45e9fbc))
* trim derivable content from CLAUDE.md and split out scripts/ ([6eb8a04](https://github.com/ravensorb/bmad-extensions/commit/6eb8a043f7754fe09af95da1514785663db9caed))


### Testing

* **infra:** close check 4's three measured escapes, and gate marketplace.json's dependencies ([6d281ad](https://github.com/ravensorb/bmad-extensions/commit/6d281ade8312b7bfc74837677c5efcbf87bafcc5))
* **infra:** pin the seven check-17 decisions an 81-mutation sweep found unpinned ([1f3b518](https://github.com/ravensorb/bmad-extensions/commit/1f3b51818d9136e2d3eaf35b4c19e300debd2fe4))
* **infra:** run the real config resolver in smoke:install, and guard its workdir ([4f96229](https://github.com/ravensorb/bmad-extensions/commit/4f96229cfb56fcffba5392b93716ea2d3020e67a))
* **l3io-pm:** assert the notice lock ordering in-process, deleting the timing margin ([a5a7766](https://github.com/ravensorb/bmad-extensions/commit/a5a7766aa4aada6adca4cb114f93e6056672e389))
* **l3io-pm:** replace the tuned notice race test with a deterministic one, finish the prose sweep ([6b7b65c](https://github.com/ravensorb/bmad-extensions/commit/6b7b65c93e336bbc702970d4fa07c98f9cc8b2b9))

## [2.5.2](https://github.com/ravensorb/bmad-extensions/compare/2.5.1...2.5.2) (2026-09-17)


### Fixes

* **l3io-pm,l3io-util,l3io-arch:** always invoke pm-status.py via uv run ([667a918](https://github.com/ravensorb/bmad-extensions/commit/667a9184094d373afcd7c25bc47d7b51baf12330))


### Documentation

* list every official BMad module next to the --modules flag ([3e25082](https://github.com/ravensorb/bmad-extensions/commit/3e2508267d713cab4ea331de07efea6ca652877a))

## [2.5.1](https://github.com/ravensorb/bmad-extensions/compare/2.5.0...2.5.1) (2026-09-12)


### Features

* **infra:** add check 17, every BMad dependency is declared ([768d509](https://github.com/ravensorb/bmad-extensions/commit/768d509449062063f7d042f2f7eec8c39abe85e9))
* **l3io-pm:** add deletion and claims checks to story code review ([46f3d47](https://github.com/ravensorb/bmad-extensions/commit/46f3d4768d58848761278c94682484d6ff14ead5))
* **l3io-util:** add the check-deps doctor mode ([85a7c7d](https://github.com/ravensorb/bmad-extensions/commit/85a7c7dee4ded869de46cae9307376c344cce870))
* **l3io-util:** declare every BMad dependency in one inventory ([65def56](https://github.com/ravensorb/bmad-extensions/commit/65def56cb525b6a3ee5ccdbd36482b42e3443fbd))
* **l3io-util:** verify installed BMad skills against the inventory ([d052314](https://github.com/ravensorb/bmad-extensions/commit/d0523141995f4b98d3a00ae5e079df4a23e06238))


### Fixes

* **infra:** token-bound check 17's probe arm and escape replaced_by ([85f59e0](https://github.com/ravensorb/bmad-extensions/commit/85f59e057fd5f6df14df60beb1fc05f96af314d0))
* install bmm explicitly, and stop sibling module.yaml files diverging ([104a227](https://github.com/ravensorb/bmad-extensions/commit/104a2279cf60a500c583d565dc0dcd0c13a14ec6))
* **l3io-pm:** probe both skill layouts so the arch gate stops self-skipping ([9fb6d48](https://github.com/ravensorb/bmad-extensions/commit/9fb6d48943091a394055278ca4ac95e2e08d6133))
* **l3io-pm:** resolve closure reviewers across BMad versions ([164fb95](https://github.com/ravensorb/bmad-extensions/commit/164fb95315c60ede5f6306a6fdc5cebbe7da333b))
* **l3io-pm:** resolve the dev-loop implementer instead of hard-coding it ([f001e8c](https://github.com/ravensorb/bmad-extensions/commit/f001e8cc28101e24ae2088f7a28bab631c783dbe))
* **l3io-pm:** resolve the readiness checker across BMad versions ([7df29be](https://github.com/ravensorb/bmad-extensions/commit/7df29be7cbef3c530b143841e08bab2322410365))
* **l3io-pm:** resolve the story enricher instead of hard-coding it ([f370044](https://github.com/ravensorb/bmad-extensions/commit/f370044294698fa551d1409431e8c7db80f3557c))
* **l3io-pm:** say so when the UX review phase skips, as the adversarial one does ([824819e](https://github.com/ravensorb/bmad-extensions/commit/824819ef361f2bd7d9ab660bb56355f8b60aac3d))
* **l3io-util:** close review findings in the v6.12 dependency guard ([965025b](https://github.com/ravensorb/bmad-extensions/commit/965025b8271113a8d804ce0eecc68d0ab060fc9d))
* **l3io-util:** name the module five BMad skills actually ship in ([000691e](https://github.com/ravensorb/bmad-extensions/commit/000691ecca5fda2d354a27aa318fa60f6880e502))
* **l3io-util:** reject an unknown inventory status instead of warning ([60edaf2](https://github.com/ravensorb/bmad-extensions/commit/60edaf289358bb61000a370c34b2c3d85d277ec1))


### Documentation

* **adr:** record ADR-0006, one guarded BMad dependency inventory ([ae11245](https://github.com/ravensorb/bmad-extensions/commit/ae112456df3e5532d48ec773f5b83ae86040fe86))
* correct task 14's acceptance criterion to what this machine reports ([32c660c](https://github.com/ravensorb/bmad-extensions/commit/32c660c5513fa969de522b95ebd7437879e17e7c))
* correct the migration plan for four pre-flight rulings ([1b19e30](https://github.com/ravensorb/bmad-extensions/commit/1b19e3079a8a37bf144330496ba8172c2669f5fa))
* correct three docs that still described the pre-6.12 dependency set ([1665899](https://github.com/ravensorb/bmad-extensions/commit/1665899f68d7da821f71debd23830a2e62b7956a))
* design the BMad v6.12.0 dependency migration ([d79b6fa](https://github.com/ravensorb/bmad-extensions/commit/d79b6faffcba2d658f7e64e122c3c5a4a1de5ef3))
* fix prefer/fallback direction and legacy qualifiers from review round 1 ([2e7be0f](https://github.com/ravensorb/bmad-extensions/commit/2e7be0fdb4fcb40f37f6974913f42f2f539513e6))
* give task 9 the measured violation list, not a hand-built one ([901f98b](https://github.com/ravensorb/bmad-extensions/commit/901f98bd52bf2ac2a8a2999193ac1afe8ae08363))
* **l3io-pm:** state elaboration's batching unit as the epic, not the sprint ([05b9ce9](https://github.com/ravensorb/bmad-extensions/commit/05b9ce94fae6be206add72cb23516841f6caeeec))
* make the v6.12.0 migration version-tolerant, not a switch ([505ba20](https://github.com/ravensorb/bmad-extensions/commit/505ba201b1acb4995f35d0947f45696e39eb4732))
* plan the BMad v6.12.0 dependency migration ([b0c745a](https://github.com/ravensorb/bmad-extensions/commit/b0c745a080809243d2eafff3cb65a8477e2ff1ef))
* put legacy on the same line as each dead skill name the plan prescribes ([c1834b8](https://github.com/ravensorb/bmad-extensions/commit/c1834b85a014566934ec46161cefdcb7e7eadf6a))
* qualify every remaining unqualified removed-skill mention ([d411255](https://github.com/ravensorb/bmad-extensions/commit/d411255f0ad88d79e81792c6c2ea39e0fac1a52c))
* retire stale BMad skill names outside the shared sources ([7a0eb76](https://github.com/ravensorb/bmad-extensions/commit/7a0eb765cecc3dd4dc490821e9248221f11b8e59))
* **spec:** make section 5.1 defer to the binding tolerance rule ([1cc5eb0](https://github.com/ravensorb/bmad-extensions/commit/1cc5eb04c7572d3eeb6f0760f35121cf0a5afad3))
* state BMad dependencies as they resolve on both install shapes ([3d47852](https://github.com/ravensorb/bmad-extensions/commit/3d47852759b1a6bce186c86083272b16a621413a))


### Testing

* **l3io-util:** derive check 15's planted-mode expectations from the tree ([ad087c4](https://github.com/ravensorb/bmad-extensions/commit/ad087c45cdf08d0a39add01384211ac061854f14))

## [2.5.0](https://github.com/ravensorb/bmad-extensions/compare/2.4.13...2.5.0) (2026-09-12)


### Features

* **infra:** check-docs covers the spec-align surface (check 4) and adds checks 13, 14 ([1595190](https://github.com/ravensorb/bmad-extensions/commit/159519068a0138895e241613ed14d73882c48132))
* **l3io-pm:** add sprint closure commit checkpoint ([db72d5e](https://github.com/ravensorb/bmad-extensions/commit/db72d5ee99805b23606671853620e612b03304b9))
* **l3io-pm:** adr-reserve scans docs/adr and the old ADR home before allocating ([913f199](https://github.com/ravensorb/bmad-extensions/commit/913f1997d13c189b0ffd7617063eeee147e60e09))
* **l3io-pm:** audit-issues reports backlog integrity findings 1a-1j ([4f94bc0](https://github.com/ravensorb/bmad-extensions/commit/4f94bc09d1b5fbf5f3f4075a1a0aeafb11443d12))
* **l3io-pm:** backlog item kind and ref for spec-change and spec-proposal items ([324fb3c](https://github.com/ravensorb/bmad-extensions/commit/324fb3cdd32d2021998abdf0db4629638fe6cf70))
* **l3io-pm:** dedupe appends against resolved items; flag recurrences ([4af381f](https://github.com/ravensorb/bmad-extensions/commit/4af381fececee6adca344f3f9ee805f168378108))
* **l3io-pm:** drift dispositions, epic spec sync, and the epic commit checkpoint ([e29cc68](https://github.com/ravensorb/bmad-extensions/commit/e29cc68d02079ea81b9c2a94d7ac52b846547a20))
* **l3io-pm:** list-issues reads resolved items, --all snapshot, origin_archived ([0c89afe](https://github.com/ravensorb/bmad-extensions/commit/0c89afef5e3fcdaab7a1e4f49fad3e75d7805080))
* **l3io-pm:** pm-plan offers backlog-to-story intake before readiness ([babe453](https://github.com/ravensorb/bmad-extensions/commit/babe4537ff3914c88eba6f7a8cc66b8ff3eb1231))
* **l3io-pm:** promote-issue turns BL items into an estimated story ([7126873](https://github.com/ravensorb/bmad-extensions/commit/7126873af745ca1c7469f44d1767813d3a6f9825))
* **l3io-pm:** repair-issue applies structural fixes gated on audit findings ([6916402](https://github.com/ravensorb/bmad-extensions/commit/6916402a9e8e9a7d2a16f55b1e15ef49579db611))
* **l3io-pm:** resolve-issue moves BL items to issues-resolved.yaml ([5b2af57](https://github.com/ravensorb/bmad-extensions/commit/5b2af5774cb6d4640740a7764324faba40a652ed))
* **l3io-pm:** spec inputs to the arch gate; ADRs to docs/adr; spec_alignment switch ([948d0cb](https://github.com/ravensorb/bmad-extensions/commit/948d0cb044b17d29480097607affa6da59fcb6cc))
* **l3io-pm:** spec-align adrs and check-links ([2004f66](https://github.com/ravensorb/bmad-extensions/commit/2004f66f06dae4260bc478524f25454a14db2e52))
* **l3io-pm:** spec-align check-pointers and sections (story provenance) ([75bc0fa](https://github.com/ravensorb/bmad-extensions/commit/75bc0faade86f5bd2509caf643219716b4ad6996))
* **l3io-pm:** spec-align commit with scope and anchor guards ([b320ac5](https://github.com/ravensorb/bmad-extensions/commit/b320ac53eeb6e2a0041d6be3e750ba42838a2e1d))
* **l3io-pm:** spec-align disposition and check-dispositions ([a04a0dc](https://github.com/ravensorb/bmad-extensions/commit/a04a0dc14751c7d18875c1fa40548b290e49d9cc))
* **l3io-pm:** spec-align reject and check-stale ([d5fe335](https://github.com/ravensorb/bmad-extensions/commit/d5fe335aa038eb66397ffa72ca52b724a900496c))
* **l3io-pm:** spec-align spec-sync lease ([0547f13](https://github.com/ravensorb/bmad-extensions/commit/0547f131dbb65ed4987565ec4be10b8653c53458))
* **l3io-pm:** spec-align sync-plan, --defer and propose ([d833b28](https://github.com/ravensorb/bmad-extensions/commit/d833b285f79a9450d113e4b3e64c8dbddeda0afb))
* **l3io-pm:** spec-align.py with the spec index (build) ([be2b6ee](https://github.com/ravensorb/bmad-extensions/commit/be2b6eecf2d4dacb5dc9a185891351cee4f07a18))
* **l3io-pm:** story done resolves its backlog items; set-field refuses status ([8ce41ee](https://github.com/ravensorb/bmad-extensions/commit/8ce41ee2035ee30968f561acb7158a831babf948))
* **l3io-pm:** story prep requires spec provenance pointers ([a77cd1a](https://github.com/ravensorb/bmad-extensions/commit/a77cd1ab0fb227946ad3ae7800db99f70899295b))
* **l3io-pm:** story-doc-init owns the story document skeleton ([84f33c4](https://github.com/ravensorb/bmad-extensions/commit/84f33c4741a55d8d5192ac95db7991b778fdc472))
* **l3io-pm:** update-issue re-severities an open BL item ([ff78024](https://github.com/ravensorb/bmad-extensions/commit/ff78024f1df9283ba0952cc6b5dfd36e202fe43c))
* **l3io-util:** audit-backlog.py proposes resolutions for open BL items ([d4bcba3](https://github.com/ravensorb/bmad-extensions/commit/d4bcba345235a93b5552d6a0268268e94958e280))
* **l3io-util:** doctor migrate-adrs mode and spec-alignment health Checks 15-19 ([6a2a691](https://github.com/ravensorb/bmad-extensions/commit/6a2a691102c754c1d3ce5eafc41df20e3cb94312))
* **l3io-util:** spec-align migrate-adrs (old epic ADR home -> docs/adr) ([b82e19b](https://github.com/ravensorb/bmad-extensions/commit/b82e19b34670c1c131eee37dc793006a2919fb14))
* **l3io-util:** triage mode audits the backlog and resolves what is fixed ([c760e69](https://github.com/ravensorb/bmad-extensions/commit/c760e69d7389ed529f63f4a2baef0c0a862c0ebf))
* **l3io-util:** triage spec pass; spec items skip the mechanical audit; ADR allocation in arch-review ([6941094](https://github.com/ravensorb/bmad-extensions/commit/6941094b3e208a67bf27fe5674d9cde9ed5566d9))


### Fixes

* **infra:** check 14 exemption must qualify the path, not just share the line ([ccb3352](https://github.com/ravensorb/bmad-extensions/commit/ccb3352accdc2e24142929edfc8c94585684b289))
* **infra:** correct the doctor mode count and enforce it with check 15 ([394cbd4](https://github.com/ravensorb/bmad-extensions/commit/394cbd41ba488f87072f5f5f64d6ff9ddc1ee888))
* **l3io-pm:** apply resolved-first, single_open and the 1j claim gate in audit and repair ([1f17085](https://github.com/ravensorb/bmad-extensions/commit/1f17085a27b263b618fe74b59aad6048a2a29d0b))
* **l3io-pm:** check-links refuses an unparseable --epic ([e1e2628](https://github.com/ravensorb/bmad-extensions/commit/e1e26288db579c15ea008af7cbd99086eadcc0c8))
* **l3io-pm:** close final-review minors M1, M5, M7 and pin lock-hold identity ([6817749](https://github.com/ravensorb/bmad-extensions/commit/6817749d6538ce84deb2c06108feb52f6b677f77))
* **l3io-pm:** compare a lock holder's session_id exactly in promote ([c8d5c13](https://github.com/ravensorb/bmad-extensions/commit/c8d5c13233b0e79ca34b27b2960b57bb1c273c4c))
* **l3io-pm:** compute_story_estimate mutates the node only after pricing succeeds ([8f114fd](https://github.com/ravensorb/bmad-extensions/commit/8f114fdc0427f4c3ff1710c9a717792374247703))
* **l3io-pm:** deterministic lock-wait tests; enforce epic-lock order ([a22a561](https://github.com/ravensorb/bmad-extensions/commit/a22a56183bf5ebdadb43380b98f68be8e66f8d2c))
* **l3io-pm:** done hook normalises resolves inside its catch-all ([3bda361](https://github.com/ravensorb/bmad-extensions/commit/3bda361e70d21916a555a49a148663f4966335e4))
* **l3io-pm:** every backlog producer records a pointer; closure promotes via update-issue ([5616adf](https://github.com/ravensorb/bmad-extensions/commit/5616adf533c7bde55f5f0e765cb4fc0a84ccba0a))
* **l3io-pm:** every epic.yaml write holds epic_node_lock ([5e9daa9](https://github.com/ravensorb/bmad-extensions/commit/5e9daa9ee388d34eca0696233cf3ffa312364bf3))
* **l3io-pm:** final-review minors — spec ID format, empty --spec-paths, dimension names, docstring check, recovery test ([6a4e37d](https://github.com/ravensorb/bmad-extensions/commit/6a4e37dc8905444fdd38bb9619130a69445eeece))
* **l3io-pm:** item field order, audit docstring, and the 1k test plant ([58735d1](https://github.com/ravensorb/bmad-extensions/commit/58735d1643d3393676da1ac5c83401ebe30c9c18))
* **l3io-pm:** keep pm-status lock files out of git via state/.gitignore ([a87edee](https://github.com/ravensorb/bmad-extensions/commit/a87edeeb0a8ca3fa5eba6db4a856f32fcebdc774))
* **l3io-pm:** list-issues --all takes no lock when no issue file exists ([8579f2e](https://github.com/ravensorb/bmad-extensions/commit/8579f2ed37cb2b9efe88c918e9a744cc40211eb6))
* **l3io-pm:** make a same-severity update a no-op and tag link's event ([e7689a8](https://github.com/ravensorb/bmad-extensions/commit/e7689a86bac0b4b7e7877531de4572ba9ebae984))
* **l3io-pm:** make the reject recovery command runnable and parse git file lists by line ([4b82565](https://github.com/ravensorb/bmad-extensions/commit/4b825659b612128033cfdcc911761dba82eb61e7))
* **l3io-pm:** match git's single-CR strip and BOM handling in the lock-rule check ([050889f](https://github.com/ravensorb/bmad-extensions/commit/050889fe518b18b5b11c1a0e3e8e289b148ff74d))
* **l3io-pm:** never reuse a BL key -- per-epic next high-water allocator ([54f4ff0](https://github.com/ravensorb/bmad-extensions/commit/54f4ff02d1bf56665767a72be98c2645be5c293f))
* **l3io-pm:** pm-sync docs state pull's completed-only done rule ([ecbf1dd](https://github.com/ravensorb/bmad-extensions/commit/ecbf1ddad3b5107bf721aaa23088d02b3b35cc4f))
* **l3io-pm:** pm-sync pull marks done only for issues closed as completed ([88a4532](https://github.com/ravensorb/bmad-extensions/commit/88a4532b2341198712cb69b1379868efea164c0d))
* **l3io-pm:** promote refuses a foreign lock it cannot evaluate ([a0fd1c4](https://github.com/ravensorb/bmad-extensions/commit/a0fd1c4a384a22601b73e23a1e9e4c7f942b497f))
* **l3io-pm:** promote-issue validates items under issues_lock before writing; strict resume ([a050595](https://github.com/ravensorb/bmad-extensions/commit/a0505958f130635ba6ce55f66ce07eb540bc33db))
* **l3io-pm:** read .gitignore the way git does, read before writing, and stay in the state root ([9095e08](https://github.com/ravensorb/bmad-extensions/commit/9095e08a3dd9c4f286939b1fc5d58de92c9a9936))
* **l3io-pm:** refuse a story node that is not a mapping or not valid UTF-8 ([237b515](https://github.com/ravensorb/bmad-extensions/commit/237b515528af4aadea1bb561082432e6ea762702))
* **l3io-pm:** refuse an ADR link into a non-architecture spec (ADR-0004) ([9c1ea2a](https://github.com/ravensorb/bmad-extensions/commit/9c1ea2ad871f03a63886a3ca79daa87f0911f7a3))
* **l3io-pm:** refuse an unreadable story node instead of a traceback ([effc567](https://github.com/ravensorb/bmad-extensions/commit/effc567966381b1a1766e0a303719127d36dad8a))
* **l3io-pm:** refuse cross-epic resume and treat archived undone claims as dead ([9507ab7](https://github.com/ravensorb/bmad-extensions/commit/9507ab77836caa70f319ed480eaba325ca45a062))
* **l3io-pm:** refuse set-field on a parent path of a derived field ([26df98d](https://github.com/ravensorb/bmad-extensions/commit/26df98dd8959a32ac9d9cb8e1f45bab3f870e0c1))
* **l3io-pm:** refuse set-field writes to any sub-path of a derived field ([0c0adaf](https://github.com/ravensorb/bmad-extensions/commit/0c0adafd50aa3badc0f73bd6ec20326827884750))
* **l3io-pm:** report next: aliases as 1e and bound reseed to the key space ([e0e9b1c](https://github.com/ravensorb/bmad-extensions/commit/e0e9b1c784cbc94acc9240ad2faf5002dc0e1177))
* **l3io-pm:** require a real ADR link and roll back pointer rewrites on a failed commit ([1108a54](https://github.com/ravensorb/bmad-extensions/commit/1108a54dacb03f14d8fa54e814c3cc8490a374e0))
* **l3io-pm:** roll back chained pointer renames in reverse and tighten the ADR link check ([c037501](https://github.com/ravensorb/bmad-extensions/commit/c0375016580eb3a402aaaada38f89bb83dbb3419))
* **l3io-pm:** share check-lock's verdict with promote, and tighten issue-verb outputs ([723f5c1](https://github.com/ravensorb/bmad-extensions/commit/723f5c1b7827dcc8d4c54f29cad293931db7a43a))
* **l3io-pm:** stage the spec index only when it exists ([6a2c285](https://github.com/ravensorb/bmad-extensions/commit/6a2c28591cbb84a78331319a65fdb96df74c8f90))
* **l3io-pm:** story-doc-init creates atomically and never clobbers ([e5b6e81](https://github.com/ravensorb/bmad-extensions/commit/e5b6e818d86f5c5c7fde872b1cf495ca26d3b0eb))
* **l3io-pm:** update-issue refuses a resolved key even with a stale open copy ([7aaef39](https://github.com/ravensorb/bmad-extensions/commit/7aaef392cb122dd4f676b90118226268e8552597))
* **l3io-pm:** use ruamel.yaml in test_calibration_show_warns_on_mixed_models ([a531640](https://github.com/ravensorb/bmad-extensions/commit/a5316401cb7472badb52ba9aea65104b34d8a3ab))
* **l3io-util:** audit-backlog matches code-marker paths containing spaces ([13d32dc](https://github.com/ravensorb/bmad-extensions/commit/13d32dc9152cb2c59b82359d0e442f099423e5d8))
* **l3io-util:** check every path the migration writes and report touched paths on a failed commit ([0c6363a](https://github.com/ravensorb/bmad-extensions/commit/0c6363aa8e8ae4999577e1de541f67977c907af0))
* **l3io-util:** doctor housekeeping fixes -- mass-missing guard, Check 13 gating, SKILL.md orphan ([f4772ca](https://github.com/ravensorb/bmad-extensions/commit/f4772ca71ef8b706b0aa3853a6de9bc3674f35ec))
* **l3io-util:** key health Check 17 on the ADR homes, not the spec index ([476331c](https://github.com/ravensorb/bmad-extensions/commit/476331c63bdc34086f6bbc062588e999c60b3d22))
* **l3io-util:** refuse a dirty migration, report uncommitted rewrites, cover collisions ([6bce0e6](https://github.com/ravensorb/bmad-extensions/commit/6bce0e635198e55c11e5e964a3da394c44f842ad))


### Refactoring

* **l3io-pm:** drop allocator helpers superseded by IssueStore ([8ab2f99](https://github.com/ravensorb/bmad-extensions/commit/8ab2f99bac43c3b5dea8df5154c408e030e7b814))
* **l3io-pm:** non-exiting estimate cores behind the estimate CLI ([d5d9164](https://github.com/ravensorb/bmad-extensions/commit/d5d91640e77b95c3873dbe3bc8543735e6557a44))


### Documentation

* add issue lifecycle and backlog intake design spec ([ff20352](https://github.com/ravensorb/bmad-extensions/commit/ff203528037c32aeff3c5259787a581bb0abe33e))
* add issue lifecycle implementation plan ([5378982](https://github.com/ravensorb/bmad-extensions/commit/5378982620eb6415f21d7a5c2371764e1d5d8f51))
* add skills-and-sequence, troubleshooting, glossary and limits ([470add9](https://github.com/ravensorb/bmad-extensions/commit/470add9632d4af51a49ac8d1340601565d2c86da))
* **adr:** ADR-0004 spec edit authority, ADR-0005 one ADR home ([0e3b3bb](https://github.com/ravensorb/bmad-extensions/commit/0e3b3bbe5c6e2b7748f08b6749a8bea6e911e252))
* append post-review amendments to the issue-lifecycle spec ([ee92be9](https://github.com/ravensorb/bmad-extensions/commit/ee92be942791dc9c41b4845a7869829b56df7140))
* approve issue lifecycle spec; accept ADR-0002 and ADR-0003 ([1f438fa](https://github.com/ravensorb/bmad-extensions/commit/1f438fa3e473c9baedead5ab9b7133cba26ab74a))
* complete the PM config table and README's doctor surface ([26ef911](https://github.com/ravensorb/bmad-extensions/commit/26ef9119ffdc12f8bf0ac60c81240cec201f79e4))
* correct the test-suite paragraph for the third shared suite ([90de554](https://github.com/ravensorb/bmad-extensions/commit/90de55407fc72960c0191f3cc1767645d9de4f95))
* describe the backlog lifecycle, both issue files, and check 11 ([e12a941](https://github.com/ravensorb/bmad-extensions/commit/e12a9411d1f5ea26caf1798d975e134d0eb66f7c))
* document spec_alignment/spec_paths and arch-review's ADR numbering ([7caeeb2](https://github.com/ravensorb/bmad-extensions/commit/7caeeb279d8d87c9a1e9c6e362698a1e9cea992b))
* document the triage spec pass and backlog item kinds ([c5f41f0](https://github.com/ravensorb/bmad-extensions/commit/c5f41f07f730f138881424131762a3847263a910))
* give contributors the repo's invariants, and warn that split-status is not enough ([4baa86c](https://github.com/ravensorb/bmad-extensions/commit/4baa86cf38f435a349cef13cefb77abb2eb374ff))
* **l3io-pm:** audit-issues covers 1a-1k in the reference tables ([5ab3738](https://github.com/ravensorb/bmad-extensions/commit/5ab37386f2670ee1736e88af363cc3a8e5021905))
* **l3io-pm:** audit-issues docstrings state the Ruling 9 lock rule ([3afee84](https://github.com/ravensorb/bmad-extensions/commit/3afee84005a092f37dd52afae1795a595dcb7a47))
* **l3io-pm:** close final-review doc findings I1-I3, 5a, M2-M4, M9 ([c53d190](https://github.com/ravensorb/bmad-extensions/commit/c53d19058c0906a78f9279034ddf4ff8a8d2cf60))
* **l3io-pm:** correct audit-scope and recovery wording after the fix-wave re-review ([d90ed77](https://github.com/ravensorb/bmad-extensions/commit/d90ed7755e7dca6d27ffb3b9a9c443e444ac4e32))
* **l3io-pm:** describe the final-review fixes — dead claims, 1j gate, lock span, outputs ([5b3242f](https://github.com/ravensorb/bmad-extensions/commit/5b3242f04b7b03fa600a661987643b9c8ac7ff56))
* **l3io-pm:** document intake's exit-1 path and batches A/D1's user-visible changes ([64db939](https://github.com/ravensorb/bmad-extensions/commit/64db939b7c974571ce0d552ea4ab0736e5ce959b))
* **l3io-pm:** document spec alignment, spec-align.py and the one ADR home ([7a27677](https://github.com/ravensorb/bmad-extensions/commit/7a276772ad7bce9189526cd5a4590d5dcc8ed557))
* **l3io-pm:** document the Help and Sync skills and the severity vocabularies ([f32202c](https://github.com/ravensorb/bmad-extensions/commit/f32202c3b9468870d0b974230df2ea426f7058e3))
* **l3io-pm:** note set-actual --cost's refusal-before-lock ordering (batch D1 fix round 1) ([7a0bdd3](https://github.com/ravensorb/bmad-extensions/commit/7a0bdd3f2e6f4c937467e7636f67afc19327eb39))
* **l3io-pm:** scope _ensure_lock_ignore's docstring to state roots ([a1830ba](https://github.com/ravensorb/bmad-extensions/commit/a1830bab0767325e495568a6e96dbeaf63440794))
* **l3io-pm:** spec-alignment design — spec index, provenance, drift sync, one ADR home ([45c7a57](https://github.com/ravensorb/bmad-extensions/commit/45c7a57dab88360cdfab55b20acaa4b811f748e3))
* **l3io-pm:** spec-alignment implementation plan (20 tasks) ([3226069](https://github.com/ravensorb/bmad-extensions/commit/32260694594221c098110f945bf79e51162e1c41))
* **l3io-pm:** state that a bare --file outside a state root skips the lock ignore ([4853649](https://github.com/ravensorb/bmad-extensions/commit/4853649ad7798f76d9e75c6689bf45671064da93))
* **l3io-pm:** state the resolved-match severity rule unambiguously ([f4ee29d](https://github.com/ravensorb/bmad-extensions/commit/f4ee29d519f54c5d2488e08061431ccb1dbeb1e6))
* **l3io-pm:** the first lock inside the state root writes the ignore rule ([d2e14b9](https://github.com/ravensorb/bmad-extensions/commit/d2e14b9c5d8669c982e7f13ff17d74b5ab552e92))
* **l3io-pm:** the per-epic arch dir holds the gate review, not ADRs ([9112519](https://github.com/ravensorb/bmad-extensions/commit/9112519aa250d48c2388a0f5ebaaf41caefe34cc))
* **l3io-pm:** untrack committed lock files at the checkpoint and in doctor ([3a6331c](https://github.com/ravensorb/bmad-extensions/commit/3a6331c66802904aed192456e62224161e32a86e))
* **l3io-util:** file migrate-adrs as a one-time migration in both lists ([517612c](https://github.com/ravensorb/bmad-extensions/commit/517612cd3bceff2bdb0b7a753c82397ba47a814a))
* **l3io-util:** say what health-check scans may write, and close Check 14's gaps ([e0c2cb4](https://github.com/ravensorb/bmad-extensions/commit/e0c2cb415909daff7255839d2abbf771c57340ed))
* lead with why, route by audience, and correct the front door ([1dd61cc](https://github.com/ravensorb/bmad-extensions/commit/1dd61cce570f3df17439eb0be0eb95c761f630dc))
* revise issue lifecycle spec after arch and edge-case reviews ([79d5313](https://github.com/ravensorb/bmad-extensions/commit/79d531360de96a4c6ad13ff5bc604da32f32e2d4))
* state append-issue's dedupe rule unambiguously ([de824f9](https://github.com/ravensorb/bmad-extensions/commit/de824f9f60801dfd6d7841c0cd14de150f39b5da))


### Maintenance

* apply the MIT licence and declare it in package.json ([390b2d2](https://github.com/ravensorb/bmad-extensions/commit/390b2d25c14220ab92bc83aad7dc24d87c9b635f))
* merge origin/main into local history ([9dfcb60](https://github.com/ravensorb/bmad-extensions/commit/9dfcb60a02ee6880798eed0f9a8ce82de5d59c9a))


### Testing

* **infra:** exact guard restore, root-safe read-only test, scoped class docstring ([dc0b50c](https://github.com/ravensorb/bmad-extensions/commit/dc0b50c7dda781d75e14a9bfb90acc3d391d7654))
* **infra:** extend the temp-dir guard to child processes; run step-04's git add in 7b ([f717531](https://github.com/ravensorb/bmad-extensions/commit/f717531d86c4417d6adfe4c03b3f57a02c522342))
* **infra:** stop the Python suites leaking temp dirs, and fail the run on a leak ([6d4a16c](https://github.com/ravensorb/bmad-extensions/commit/6d4a16c71eeab43f1a1a1e04a2f46c726b5b478f))
* **l3io-pm:** close issue-lifecycle coverage gaps; deterministic lock-scope tests ([1ae4c83](https://github.com/ravensorb/bmad-extensions/commit/1ae4c837a8184b74073be11205ad9c8f7dab208f))
* **l3io-pm:** cover the spec-issue duplicate retry and the bad-epic refusal ([38b24a3](https://github.com/ravensorb/bmad-extensions/commit/38b24a3c1b7e99c9c6ffc3b198b992c196a7fd42))
* **l3io-pm:** prove promote writes a story node and its estimate in one save ([32a1d90](https://github.com/ravensorb/bmad-extensions/commit/32a1d905bf974f0d99be8b46f1261fda699690c2))
* **l3io-pm:** silence the suites' stderr noise at its sources ([c60042c](https://github.com/ravensorb/bmad-extensions/commit/c60042cab2a4666bc30e06800c690d18798a4a46))


### CI/CD

* check 11 finds append-issue invocations without tracking fences ([3909bd2](https://github.com/ravensorb/bmad-extensions/commit/3909bd2b37b54762ac0ee38e71299de4a407462a))
* check 11 joins continued lines before matching invocations ([b9d9840](https://github.com/ravensorb/bmad-extensions/commit/b9d9840b4c21e57efa5eba32e4b8771e9d3ad526))
* check 11 requires a pointer on every backlog producer; node:test; Node 24 ([6dbbd4b](https://github.com/ravensorb/bmad-extensions/commit/6dbbd4b113096cfec2836df0f4c4394c723c775c))
* check:docs check 12 enforces ADR-0001's pm-status.py size limit ([fa85a39](https://github.com/ravensorb/bmad-extensions/commit/fa85a39bb9407e25c28389fe4a801a92ee7a3ce3))

## [2.4.13](https://github.com/ravensorb/bmad-extensions/compare/2.4.12...2.4.13) (2026-09-01)


### Features

* **l3io-pm:** add --runtime codex enforcement with 3-class token capture ([31a5d1d](https://github.com/ravensorb/bmad-extensions/commit/31a5d1d4631633fabbcc5b83558e217612d50811))
* **l3io-pm:** add --runtime copilot enforcement with scalar token capture ([45ca2ee](https://github.com/ravensorb/bmad-extensions/commit/45ca2eebecd397a0fcad22d215a090c32a48cfb5))
* **l3io-pm:** add list-plan mode to l3io-help ([fc2e895](https://github.com/ravensorb/bmad-extensions/commit/fc2e89517061a8d6e4b46f0e809456314aa161f8))
* **l3io-pm:** extend runtime choices to codex and copilot, add OpenAI token rates ([e19f15f](https://github.com/ravensorb/bmad-extensions/commit/e19f15fe6a7340faaffd251e8694d801e81784c2))
* **l3io-pm:** extend runtime detection to codex and copilot in step-00-activate ([10b006e](https://github.com/ravensorb/bmad-extensions/commit/10b006eea6da72f33570c87cf7e9e7329f9592db))
* **l3io-pm:** multi-runtime estimation support (codex, copilot) ([6b70f18](https://github.com/ravensorb/bmad-extensions/commit/6b70f18eafbb150850c11a1c51a646006ab29bb1))
* **l3io-util:** add bootstrap-state mode for bmad-create-story projects ([e53d91e](https://github.com/ravensorb/bmad-extensions/commit/e53d91ed768e387e8eb24a9c80ed59978a2521b6))
* **l3io-util:** align multi-runtime support with BMad AGENTS.md convention ([7467e44](https://github.com/ravensorb/bmad-extensions/commit/7467e44222b2f7a3927e3eabb8085329f170ee62))
* **l3io-util:** detect and surface planning-vs-execution model mismatch ([96ca4cd](https://github.com/ravensorb/bmad-extensions/commit/96ca4cd204bd3900b51c00b471a15b6776c0c223))
* **l3io-util:** update OpenAI token rate table for GPT-5.6 family ([dec306f](https://github.com/ravensorb/bmad-extensions/commit/dec306ffe2dd92997619bf39a6d69bf003f59782))


### Fixes

* **l3io-pm:** add verify runtime choice tests and TOKEN_RATES assertions ([a7072a3](https://github.com/ravensorb/bmad-extensions/commit/a7072a32527fd686329f63de6b4f3270c86fd3b6))
* **l3io-pm:** create story artifact file if absent before elaboration ([ce8c1a2](https://github.com/ravensorb/bmad-extensions/commit/ce8c1a23e08deb4345322b4c0f2d11ebf49dfa4c))
* **l3io-pm:** detect artifact-only stories before readiness check ([462390e](https://github.com/ravensorb/bmad-extensions/commit/462390e606d62ac370a9d2f9d1146b49de3060f9))
* **l3io-pm:** fix codex tokens-na error message, update CLI docstring ([43fdc2e](https://github.com/ravensorb/bmad-extensions/commit/43fdc2eb451021e44e73b87f3e398f8c7df16a1f))


### Documentation

* add estimation-guide for multi-runtime token capture ([4e6cf36](https://github.com/ravensorb/bmad-extensions/commit/4e6cf36c4ab2e7679bcee98abf5b95579a09c2c9))
* **l3io-pm:** add implementation plan for bootstrap and story-creation fixes ([50d5e8c](https://github.com/ravensorb/bmad-extensions/commit/50d5e8c4f22ff0d3d7705d857632516beefb0202))
* **l3io-pm:** update metrics-contract §3 with four-runtime capture procedures ([3a09194](https://github.com/ravensorb/bmad-extensions/commit/3a09194ee15ee7e8e1d54c813a3d0bd62d081dd2))
* **l3io-util:** document cross-runtime planning and model mismatch behavior ([9d678e3](https://github.com/ravensorb/bmad-extensions/commit/9d678e3d0fe0d9a279dbb50b1a120ac126fbb991))
* **readme:** clarify post-install step and tighten upgrading section ([72b7883](https://github.com/ravensorb/bmad-extensions/commit/72b788373c4bdcef3d0855aa39eb6df98bece24b))


### Maintenance

* regenerate payload manifests after metrics-contract docs update ([37c3a8f](https://github.com/ravensorb/bmad-extensions/commit/37c3a8fb6d59923adca6017ae390b578bcaf644a))
* **release:** sync manifests and payload copies after multi-runtime estimation ([47d5e9e](https://github.com/ravensorb/bmad-extensions/commit/47d5e9e63b55f374628e3f1b8512bca0b45c2f92))

## [2.4.12](https://github.com/ravensorb/bmad-extensions/compare/2.4.11...2.4.12) (2026-08-31)


### Features

* **l3io-pm:** add max_turns_per_story soft cap to customize.toml ([4f328e0](https://github.com/ravensorb/bmad-extensions/commit/4f328e0ad6bc45b1606a74c7b730eb0e9b8d5601))
* **l3io-pm:** add per-story turn cap to agent_contract ([abd53e7](https://github.com/ravensorb/bmad-extensions/commit/abd53e7ed663ab752d5306531096615862454bbd))
* **l3io-pm:** bind six per-role model keys at activation ([fb4976c](https://github.com/ravensorb/bmad-extensions/commit/fb4976cd06264c050970fd266487a212d25ee980))
* **l3io-pm:** model_review routing and two-tier test strategy in dev loop ([d0e9384](https://github.com/ravensorb/bmad-extensions/commit/d0e938429315c61b58f214477b256bbaa3b16fad))
* **l3io-pm:** per-role model routing in epic loop dispatch (prep/story/closure) ([f647692](https://github.com/ravensorb/bmad-extensions/commit/f647692a184fc6814417f4fec006a2b784e850d2))


### Fixes

* **ci:** guard max_turns_per_story doc quote in check:docs config-values check ([2a2938c](https://github.com/ravensorb/bmad-extensions/commit/2a2938c614b20adce1d9ed145bf7ca0c5130268f))


### Documentation

* add cost-optimization model routing and turn-reduction design spec ([e38f474](https://github.com/ravensorb/bmad-extensions/commit/e38f47411de030056f184a6a516833cd80451e64))
* add implementation plan for cost optimization model routing ([49cc718](https://github.com/ravensorb/bmad-extensions/commit/49cc718ebc7dfff92be4a51e7fe38883411d8619))
* **l3io-pm:** document per-role model routing config keys and turn cap binding ([8d4d67c](https://github.com/ravensorb/bmad-extensions/commit/8d4d67c8c772b2c412090c07d1009438ec5e4a41))


### Maintenance

* **l3io-pm:** sync shared steps and regenerate manifests after model routing changes ([c36c0e0](https://github.com/ravensorb/bmad-extensions/commit/c36c0e06d29a16a0f4627e5ce81cfe02a86fbb09))

## [2.4.11](https://github.com/ravensorb/bmad-extensions/compare/2.4.10...2.4.11) (2026-08-29)


### Features

* **l3io-util:** wire calibration redrive into the doctor's health check ([ee4643a](https://github.com/ravensorb/bmad-extensions/commit/ee4643ae5e263a5c8aec5feccc412164b41bfef5))

## [2.4.10](https://github.com/ravensorb/bmad-extensions/compare/2.4.9...2.4.10) (2026-08-27)


### Features

* **l3io-pm:** add epic-level security review to epic closure ([d30729a](https://github.com/ravensorb/bmad-extensions/commit/d30729a157c24bec8fb2954329b52da2d49694a6))


### Fixes

* **l3io-pm:** scope redteam to a seed set, not a diff fence, at sprint closure ([e26f0e8](https://github.com/ravensorb/bmad-extensions/commit/e26f0e8f88109b64a6b6eaefbfed71710039d0f3))


### Documentation

* correct arch-drift severity vocabulary in two docs ([5abd635](https://github.com/ravensorb/bmad-extensions/commit/5abd6359d69041748cde50221009c98690986341))

## [2.4.9](https://github.com/ravensorb/bmad-extensions/compare/2.4.8...2.4.9) (2026-08-26)


### Fixes

* **l3io-arch:** correct closure gate mode and severity vocabulary ([dcdc49a](https://github.com/ravensorb/bmad-extensions/commit/dcdc49a54b154426d8746443c6d5b6dc13660d44))
* **l3io-pm:** enforce mutual exclusion in the epic ownership lock ([78871b7](https://github.com/ravensorb/bmad-extensions/commit/78871b7dbc4d59e1bdfc23cce2a69ff7b29817eb))
* **l3io-sec:** correct sanctum path assertion in orphaned test ([8b7c51b](https://github.com/ravensorb/bmad-extensions/commit/8b7c51b1be887b1ade0a09b9e4031f996331f917))
* **l3io-sec:** make sanctum creation test call the real entry point ([dee233e](https://github.com/ravensorb/bmad-extensions/commit/dee233ed05f2bae3ce670dfcc665c6aa28180dad))
* **l3io-util:** make util-doctor own pm-status.py self-install, detect staleness in pm-help ([ba1ce70](https://github.com/ravensorb/bmad-extensions/commit/ba1ce70e186b0e6db238ba13cb404f11e0eb0be5))
* **l3io-util:** stop the legacy migration inventing tests_passing ([016ab9d](https://github.com/ravensorb/bmad-extensions/commit/016ab9d7252c30ad1a3b4a0db884c65afcd266ff))


### Documentation

* correct seven verified defects in first-read docs ([421912d](https://github.com/ravensorb/bmad-extensions/commit/421912d44ee2014d1cbae571c44dd2e06eba8a0b))
* correct twelve verified defects across four reference docs ([984abf7](https://github.com/ravensorb/bmad-extensions/commit/984abf76fd3cff8ddd24edccb52c39d0b590e8d1))
* fix thirteen verified defects in CLAUDE.md and status-files.md ([34bad28](https://github.com/ravensorb/bmad-extensions/commit/34bad28257f19ed5f19ae427297b39909049e9c0))
* **l3io-pm:** document 6 missing pm-status.py subcommands, guard the gap ([c93191f](https://github.com/ravensorb/bmad-extensions/commit/c93191fc4b776884922bc308c2f6b2d6e2e5acdd))
* **l3io-sec,l3io-util:** move stray decision logs out of shipped payload, correct stale claims ([c254012](https://github.com/ravensorb/bmad-extensions/commit/c25401220d56f913e932fdae90cf26356641c142))


### Maintenance

* **l3io-pm,l3io-sec,l3io-util,l3io-arch:** stop shipping test suites into skill payloads ([f62dbfd](https://github.com/ravensorb/bmad-extensions/commit/f62dbfdf9ab81efbf95d1486afe3c430523e73aa))


### CI/CD

* **l3io-sec:** wire test-init-sanctum.py into checks workflow ([33ac8b0](https://github.com/ravensorb/bmad-extensions/commit/33ac8b0d4493c93743c619ae84d5d09f6fe2ade4))

## [2.4.8](https://github.com/ravensorb/bmad-extensions/compare/2.4.7...2.4.8) (2026-08-26)


### ⚠ Incompatible CLI change

* **l3io-pm:** `pm-status.py set-field --field completion_evidence.tests_passing` now **exits 2**
  where it previously exited 0 and wrote the value. The field is derived, not asserted: record
  what you actually ran with `add-test-run --story KEY --command CMD --exit-code N`, and
  `tests_passing` is computed as `all(exit_code == 0)` over the **last run of each distinct
  command** in `completion_evidence.test_runs`. Every recorded run is kept, so a command that
  failed and was re-run green closes `true` with both runs still visible in the record.

  **Who this breaks:** any bespoke closeout script or hand-rolled automation that set
  `tests_passing` directly. Replace that one call with one `add-test-run` per test command;
  there is no flag to restore the old behavior, because a boolean an agent writes about its own
  work is not falsifiable — a story once shipped `tests_passing: true` having broken a suite it
  never ran, and the break surfaced two stories later.

  Reading is unaffected: `tests_passing` still appears in the same place with the same meaning,
  and a story that recorded no runs leaves it **absent** rather than `true`.

### Features

* **infra:** gate the per-skill payload manifests ([3f91daf](https://github.com/ravensorb/bmad-extensions/commit/3f91daf7611849facbffdeed7327585f1d4f8c2b))
* **infra:** ship a checksum manifest for payload copies ([0b74db7](https://github.com/ravensorb/bmad-extensions/commit/0b74db7c675bb7881482419ef433989d1d54f160))
* **l3io-pm:** carry read cost to the agents that pay it ([2037a84](https://github.com/ravensorb/bmad-extensions/commit/2037a84cd027c37ca1622905d3df1f784f758ba6))
* **l3io-pm:** make tests_passing derived evidence, not an assertion ([cd3a627](https://github.com/ravensorb/bmad-extensions/commit/cd3a627d87c419c6feed975f26c62a55c8452dcc))
* **l3io-pm:** write status back to the story document ([351dff0](https://github.com/ravensorb/bmad-extensions/commit/351dff08660127cefe34a0bfec91ed0d07376048))


### Fixes

* **infra:** move payload manifest to per-skill, reachable locations ([9451494](https://github.com/ravensorb/bmad-extensions/commit/945149482f47fdb252d94bac6cdf72df9bb959ed))
* **l3io-arch:** assign ADR numbers from a register before dispatch ([cfef390](https://github.com/ravensorb/bmad-extensions/commit/cfef390cbaf6f52a9c379830521006d4d650ea23))
* **l3io-arch:** never block the gate on a prompt; scope the re-validation ([c3c41e2](https://github.com/ravensorb/bmad-extensions/commit/c3c41e2e9a8762b03ed5bfdea8df031b681d9d3a))
* **l3io-pm:** bind {n} and {N} explicitly in step-05-epic-loop.md §6 ([4c26ba5](https://github.com/ravensorb/bmad-extensions/commit/4c26ba5257d1dceca3b9fe91aa715ddd63929530))
* **l3io-pm:** bind post-sprint re-estimation into the sprint loop ([cbd34a3](https://github.com/ravensorb/bmad-extensions/commit/cbd34a321b584aeb35a5508d019a076435f03ee7))
* **l3io-pm:** block on degraded plan state instead of pausing for input ([7876c08](https://github.com/ravensorb/bmad-extensions/commit/7876c08ec8a316beac5e744c6f960c539cf8f70e))
* **l3io-pm:** close remaining hand-rolled BL-key sites and a malformed-backlog crash ([debaed4](https://github.com/ravensorb/bmad-extensions/commit/debaed472237f7a44401d016621dc52108d1b497))
* **l3io-pm:** close two contract gaps that stranded live runs ([fd1b890](https://github.com/ravensorb/bmad-extensions/commit/fd1b890a88b37276101f93d93647b2fd9fb9bd09))
* **l3io-pm:** deduplicate read-cost figures and name the Files-in-scope source ([82a7333](https://github.com/ravensorb/bmad-extensions/commit/82a73332f8a36d9439b6faccdf361ff0d21c526e))
* **l3io-pm:** derive tests_passing from the last run of each command ([09527ee](https://github.com/ravensorb/bmad-extensions/commit/09527eefe37875fce4e02d3ad374ac7d59133bc5))
* **l3io-pm:** drop vestigial multi-story language and wire the review transition ([e291e0b](https://github.com/ravensorb/bmad-extensions/commit/e291e0b652b19f0d62689482fd60584d04d5e7e5))
* **l3io-pm:** give agents a procedure for required test coverage, and harden add-test-run ([d8cf76f](https://github.com/ravensorb/bmad-extensions/commit/d8cf76f70dbe177a86b721d4306ec963d366f391))
* **l3io-pm:** ignore zero closure samples on read, not only on write ([57608ae](https://github.com/ravensorb/bmad-extensions/commit/57608ae5625d421008076c7cfe224b7abbd22b85))
* **l3io-pm:** make append-issue duplicate-safe and self-allocating ([8f3040c](https://github.com/ravensorb/bmad-extensions/commit/8f3040cf69611ac5d04d7937ea6cbceff38514eb))
* **l3io-pm:** make post-sprint re-estimation do something ([1c4a8a4](https://github.com/ravensorb/bmad-extensions/commit/1c4a8a44548ab77ef6089cc3e64d082dbe5d4437))
* **l3io-pm:** move the fix-loop-cap FAILED literal after its state actions ([da9926b](https://github.com/ravensorb/bmad-extensions/commit/da9926b67e59eea79f99cb56800d401b609ec34b))
* **l3io-pm:** never let a malformed frontmatter crash sync-story-doc ([692f174](https://github.com/ravensorb/bmad-extensions/commit/692f1741672f7f2859340f5d2d79d4b409fb732f))
* **l3io-pm:** produce Files in scope on every path, and repair the story contract ([2e4c80f](https://github.com/ravensorb/bmad-extensions/commit/2e4c80fb56d118dc29261bc14d116ab0fe90760c))
* **l3io-pm:** reuse _is_number in active_closure_ratio instead of a bare isinstance check ([14264eb](https://github.com/ravensorb/bmad-extensions/commit/14264eb1142ac94e42203ee2a28dacf5c97d9182))
* **l3io-pm:** source re-estimation keys and report from real CLI output ([e9c1f8b](https://github.com/ravensorb/bmad-extensions/commit/e9c1f8be3b0b8e90a0bcc27c65be542d63faa707))
* **l3io-pm:** state the C x T cost model and bound the dev agent's reads ([3d389d7](https://github.com/ravensorb/bmad-extensions/commit/3d389d7ff822f25437248d47b17dc08bc136ee9c))
* **l3io-pm:** state what actually unblocks a red plan ([e2a9d1d](https://github.com/ravensorb/bmad-extensions/commit/e2a9d1d9b80869c849e6e22837da58e637b85378))
* **l3io-pm:** sync CLI reference derivation text and route 5c through 5d on FAILED ([8fc7793](https://github.com/ravensorb/bmad-extensions/commit/8fc77930043e43f6bd326228c7b2288307bf8369))
* **l3io-util:** point runtime directives at runtime paths ([1e39f78](https://github.com/ravensorb/bmad-extensions/commit/1e39f783c2080f0c8c6e006b72ce654b60aad23e))


### Performance

* **l3io-pm:** code review returns a pointer, not its findings ([963a3ed](https://github.com/ravensorb/bmad-extensions/commit/963a3eddc76293b334777035b9a046213b352f67))


### Documentation

* **l3io-pm:** wire append-issue's auto-allocated key into steps and reference docs ([7054f13](https://github.com/ravensorb/bmad-extensions/commit/7054f1311543b99ecfe86f366e9ecdf51bfbe9c7))
* record the new pm-status.py surface and one incompatible narrowing ([1955b54](https://github.com/ravensorb/bmad-extensions/commit/1955b549afe17744aec3de925c946d83c8e5a788))
* record the production findings report and its cleanup plan ([0382a65](https://github.com/ravensorb/bmad-extensions/commit/0382a6533eba51f8ddea8673d44b5ef368d6a92d))
* size the digest budget raise once for both tasks that need it ([98503f5](https://github.com/ravensorb/bmad-extensions/commit/98503f5703a56117b636688bb38f279a2adba005))


### Maintenance

* **infra:** ignore .superpowers/ subagent-driven-development scratch ([e0bfc92](https://github.com/ravensorb/bmad-extensions/commit/e0bfc92c7a299cab772bfe57680fea86b0fec53d))
* **l3io-pm:** regenerate payload manifests for the append-issue changes ([452bd49](https://github.com/ravensorb/bmad-extensions/commit/452bd4931fa82cc9d011c67e4e941b0cfad90983))


### Testing

* **l3io-arch:** prove adr-reserve's lock under real concurrency, refuse a corrupt reserved list ([ed1866f](https://github.com/ravensorb/bmad-extensions/commit/ed1866fa23c6270f6edeccc0b0af0ab9e36ecd0d))

## [2.4.7](https://github.com/ravensorb/bmad-extensions/compare/2.4.6...2.4.7) (2026-08-20)


### Fixes

* **l3io-pm:** scope the usage reader to a node, and find subagent transcripts ([2fb2de3](https://github.com/ravensorb/bmad-extensions/commit/2fb2de3fb81cbdc82e1e2f400845ba2bdabb9e39))
* **l3io-pm:** type fix_iterations, and add calibration redrive to repair samples ([ae692bf](https://github.com/ravensorb/bmad-extensions/commit/ae692bf118de07a5a58edf6f243320638e6f6c45))


### Documentation

* describe the run as it is now, and add the visual walk-through ([a6fe441](https://github.com/ravensorb/bmad-extensions/commit/a6fe44196c0199b8faf2866f7314bc787a668052))


### Maintenance

* remove internal identifiers and figures from the published package ([10d2360](https://github.com/ravensorb/bmad-extensions/commit/10d23600228a9cad9b2f6fde5222ee492d721e3d))

## [2.4.6](https://github.com/ravensorb/bmad-extensions/compare/2.4.5...2.4.6) (2026-08-19)


### Fixes

* **l3io-pm:** make the usage reader resolve and verify whose transcript it read ([45096c3](https://github.com/ravensorb/bmad-extensions/commit/45096c300c5ead2ee3d0af4f04d776dc05d20a90))

## [2.4.5](https://github.com/ravensorb/bmad-extensions/compare/2.4.4...2.4.5) (2026-08-19)


### Features

* **l3io-pm:** add a transcript usage reader, replacing "read the usage fields" ([0cc3f3c](https://github.com/ravensorb/bmad-extensions/commit/0cc3f3c0f33d8479b3c0088965e1355e70b774da))


### Performance

* **l3io-pm:** forbid polling, and scope every reviewer to a diff ([db8383c](https://github.com/ravensorb/bmad-extensions/commit/db8383c3d6c1ae427aa15f5b55e04e2ede60925e))

## [2.4.4](https://github.com/ravensorb/bmad-extensions/compare/2.4.3...2.4.4) (2026-08-19)


### Fixes

* **l3io-pm:** require every technical-AC dimension, and add the library check ([0d5f7f6](https://github.com/ravensorb/bmad-extensions/commit/0d5f7f65a94a73e2fdf84119cbe2f95c9234baf4))


### Performance

* **l3io-pm:** dispatch one agent per story, and cap the fix loop at 3 ([c00dafb](https://github.com/ravensorb/bmad-extensions/commit/c00dafbef77539ba35fe2e11b17a1fd8505adf90))
* **l3io-pm:** stop paying twice for one review, and escalate the arch gate ([da51db2](https://github.com/ravensorb/bmad-extensions/commit/da51db2ad6e0c1ab633f4d0274f703f6dbee9292))

## [2.4.3](https://github.com/ravensorb/bmad-extensions/compare/2.4.2...2.4.3) (2026-08-19)


### Fixes

* **l3io-pm:** measure the tokens_k scope ratio on fresh tokens only ([76c406f](https://github.com/ravensorb/bmad-extensions/commit/76c406f671e03ba36961ceac9a7bc9d8389c3ead))


### CI/CD

* drop the full clone check:version no longer needs ([224d2ca](https://github.com/ravensorb/bmad-extensions/commit/224d2cae4c5c564bb524b0ea17b01c5f918ab8ae))

## [2.4.2](https://github.com/ravensorb/bmad-extensions/compare/2.1.5...2.4.2) (2026-08-18)

## [2.1.5](https://github.com/ravensorb/bmad-extensions/compare/2.1.4...2.1.5) (2026-08-18)


### Fixes

* **l3io-pm:** guard self-install on content, not on a version number ([fa939b7](https://github.com/ravensorb/bmad-extensions/commit/fa939b7438ed5dc9042f643677edfa0aec625d05))

## [2.1.4](https://github.com/ravensorb/bmad-extensions/compare/2.1.3...2.1.4) (2026-08-18)


### Performance

* **l3io-util:** route doctor modes from steps/ instead of inlining them ([c7b87b8](https://github.com/ravensorb/bmad-extensions/commit/c7b87b86928ae81c9e101638004646ba6b2d1692))

## [2.1.3](https://github.com/ravensorb/bmad-extensions/compare/2.1.2...2.1.3) (2026-08-18)


### Features

* **infra:** budget the activation digest ([25072d5](https://github.com/ravensorb/bmad-extensions/commit/25072d53f9bf3f11481d259e60b4b92f7eeb0dbb))
* **infra:** gate the documented metric list and tighten the CLI-surface check ([8592183](https://github.com/ravensorb/bmad-extensions/commit/85921831a15997012597a191a66fb484f7c3a6c0))
* **l3io-pm:** add a model-keyed token rate table and cost derivation ([54f1f1d](https://github.com/ravensorb/bmad-extensions/commit/54f1f1db8d8495ebdfaccfa569fccfb92292464a))
* **l3io-pm:** add hitl_hours, separating supervision time from developer effort ([c3a107d](https://github.com/ravensorb/bmad-extensions/commit/c3a107d475a762054b5e63969cc7485240d20b4a))
* **l3io-pm:** attribute orchestration spend and learn it as a fourth component ([524dd3f](https://github.com/ravensorb/bmad-extensions/commit/524dd3fa8cbe3adc0a18ccc46b6f38cd58e48728))
* **l3io-pm:** break actual spend out by story, closure, and orchestration ([dbaa49d](https://github.com/ravensorb/bmad-extensions/commit/dbaa49d12d0add938b839552969b772be9a0b071))
* **l3io-pm:** close the wait protocol over every spawn site ([3242ef3](https://github.com/ravensorb/bmad-extensions/commit/3242ef345a1333faab00c21c2429a34479c7b5ca))
* **l3io-pm:** derive estimate cost from a banded token total and observed mix ([621f235](https://github.com/ravensorb/bmad-extensions/commit/621f235e78bfea749a6a99144f4a14f6ef4aaaa1))
* **l3io-pm:** make verify recompute cost and enforce the token total invariant ([c0938cf](https://github.com/ravensorb/bmad-extensions/commit/c0938cfdc93412fe8d3327f763802123f0ce5ab1))
* **l3io-pm:** migrate calibration to the new metric shape without a version bump ([b0c5a26](https://github.com/ravensorb/bmad-extensions/commit/b0c5a263632faf8937ca200b3acd2a2f8ac3ce08))
* **l3io-pm:** record dispatch open/close events and flag stalled dispatches ([803fb28](https://github.com/ravensorb/bmad-extensions/commit/803fb28ae4164b8e7bb7df6e41f098398056a5fe))
* **l3io-pm:** roll orchestration overhead into sprint and epic estimates ([828a1e7](https://github.com/ravensorb/bmad-extensions/commit/828a1e77213c844f6b847c3e282b10ee2108b025))
* **l3io-pm:** structure actual tokens by class and derive cost from them ([57afc2f](https://github.com/ravensorb/bmad-extensions/commit/57afc2f7867c2495f4d8d27a5540654e8fdfba54))


### Fixes

* **l3io-pm:** bracket the sprint dispatch and write the real attribution rule ([ae6a8f2](https://github.com/ravensorb/bmad-extensions/commit/ae6a8f2e3cd096dfc0944f4dfd491f80e946d365))
* **l3io-pm:** close the tokens_k mapping blind spot in derive_story_sample ([401b1e8](https://github.com/ravensorb/bmad-extensions/commit/401b1e8c36271a31b1f1a0bb8dc3ba3bfe323ca2))
* **l3io-pm:** close three unfalsifiable-metric holes in set-actual, verify, and report ([6c73e03](https://github.com/ravensorb/bmad-extensions/commit/6c73e03d0d2292a2e34655bb6caaa67d7e85221b))
* **l3io-pm:** compare the closure residual against a tolerance, not exact zero ([765430d](https://github.com/ravensorb/bmad-extensions/commit/765430da031d92806746fd381387682e8fb5f748))
* **l3io-pm:** correct set-actual usage banner and KeyError message quoting ([1b5a8a4](https://github.com/ravensorb/bmad-extensions/commit/1b5a8a42492db3b47a79430c5b8cb269b6b7cbe4))
* **l3io-pm:** gate the metrics migration on a positive marker, not legacy keys ([78fb082](https://github.com/ravensorb/bmad-extensions/commit/78fb082b6fe4828a713be014d4f908517e3b1278))
* **l3io-pm:** guard observed_mix against a non-mapping calibration sample ([273a06e](https://github.com/ravensorb/bmad-extensions/commit/273a06e50d5022fea348bd5de22820f86691d1d2))
* **l3io-pm:** guard the orchestration sample against replay with its own marker ([6a801b5](https://github.com/ravensorb/bmad-extensions/commit/6a801b5a34c8a342ae43207203b4d3f287d1bbfb))
* **l3io-pm:** make set-estimate cost-rejection tests exercise the real path ([70911cd](https://github.com/ravensorb/bmad-extensions/commit/70911cda14f6211424544d577b9d45ae3c247b47))
* **l3io-pm:** make the closure component measure closure, not closure-plus-orchestration ([949349b](https://github.com/ravensorb/bmad-extensions/commit/949349b8a8b79b939d001e11303cf111319feb7a))
* **l3io-pm:** resolve default_model and token_rates, and pass them through ([240b5af](https://github.com/ravensorb/bmad-extensions/commit/240b5afc081b07008de0cafec9e9c4addf67294b))
* **l3io-pm:** route hitl_hours through calibration, not just storage ([66596dd](https://github.com/ravensorb/bmad-extensions/commit/66596dd9f09d91d8a026cc6d00e38e59cbdc32d9))
* **l3io-pm:** sync rate-table payload copies, document rates/dispatch, fix cmd_rates error format ([4128797](https://github.com/ravensorb/bmad-extensions/commit/41287971e350c4e88874fe156367d9d5b5e3c8b3))
* **l3io-pm:** tighten verify's cost tolerance and cover --token-rates wiring ([8cae964](https://github.com/ravensorb/bmad-extensions/commit/8cae964c6c1b63f81c31bd41ed605b153f439376))
* **l3io-util,l3io-pm:** stop two shipped skills reading and writing the retired schema ([e399f76](https://github.com/ravensorb/bmad-extensions/commit/e399f7648a81f3d6a90b86d27a58f6d699b0e174))


### Performance

* **l3io-pm:** batch story enrichment instead of spawning per story ([b01fd3b](https://github.com/ravensorb/bmad-extensions/commit/b01fd3ba36ad30427162f6f67c9d23567880b950))
* **l3io-pm:** let dispatched subagents inherit activation ([0adf95f](https://github.com/ravensorb/bmad-extensions/commit/0adf95f37be44e0a4438f783e7e5e9581f14ff7a))


### Refactoring

* **l3io-pm:** split the calibration model out of the metrics contract ([3e163cb](https://github.com/ravensorb/bmad-extensions/commit/3e163cbe96565855c03d5450dfe1295c2b67c2f2))
* **l3io-pm:** unify estimate time_hours and actual elapsed_hours to one name ([b94fff3](https://github.com/ravensorb/bmad-extensions/commit/b94fff34cb786055a3f59036900a3369e0c310d8))


### Documentation

* **l3io-pm:** add the metrics model rework design and implementation plan ([5ff1e8e](https://github.com/ravensorb/bmad-extensions/commit/5ff1e8e7b1c05db2e4bd10afc93da7d2723d420e))
* **l3io-pm:** document the five-metric model, derived cost, and orchestration ([5c01104](https://github.com/ravensorb/bmad-extensions/commit/5c01104b887a57a255ee125b924fbf578cb4499b))
* **l3io-pm:** fix two factual errors in the metrics contract from review ([9a529d5](https://github.com/ravensorb/bmad-extensions/commit/9a529d57f7b0d5a15d856e6b11bea66f9514e2ca))
* **l3io-pm:** make the no-in-memory-handoff rule operative for subagents ([55e6a45](https://github.com/ravensorb/bmad-extensions/commit/55e6a459296794e0c970b51cf674fbfac664cbb8))
* **l3io-pm:** recompute every cost in the shipped schema examples from the rate card ([c685ee5](https://github.com/ravensorb/bmad-extensions/commit/c685ee50a3d1c31f09045d9aa8faa33e8218a183))


### Maintenance

* **l3io-pm:** bump pm-status.py to 2.4.0 so self-install propagates this fix wave ([8849d34](https://github.com/ravensorb/bmad-extensions/commit/8849d347b683d8b226261632948c647b6c4ca290))

## [2.1.2](https://github.com/ravensorb/bmad-extensions/compare/2.1.1...2.1.2) (2026-08-17)


### Features

* **infra:** check the documented CLI surface and inline config values ([40f573e](https://github.com/ravensorb/bmad-extensions/commit/40f573e42a139d1d06bbacbb2556bf348d24496c))
* **l3io-pm:** filter the progress report by state folder ([88e1417](https://github.com/ravensorb/bmad-extensions/commit/88e14173ae01d182c491a06fe38db75a4f0927a6))

## [2.1.1](https://github.com/ravensorb/bmad-extensions/compare/2.1.0...2.1.1) (2026-08-17)


### Features

* **infra:** gate documentation against the code it describes ([4ad0b1a](https://github.com/ravensorb/bmad-extensions/commit/4ad0b1af0b064535068807471a4cfb7fab4c43ab))
* **l3io-pm:** scale the fix-loop cap to work type ([a1a2438](https://github.com/ravensorb/bmad-extensions/commit/a1a2438e4e621c74733952a23aa61f36fc71cd6f))


### Fixes

* **l3io-pm:** bind max_fix_iterations in headless sprints, drop ATDD refs ([156ee5c](https://github.com/ravensorb/bmad-extensions/commit/156ee5c0b5caf9532cb76cb6c4312afff45b4389))
* **l3io-pm:** correct the activation digest's verify routing and four related nits ([89bf51d](https://github.com/ravensorb/bmad-extensions/commit/89bf51d699a3857fa7b7b7d64b6e322ca8244b51))


### Performance

* **l3io-pm:** add an operative digest to activation ([9f8da53](https://github.com/ravensorb/bmad-extensions/commit/9f8da5395d31fd6e9b35b43ba1fceeb6d04f09d4))
* **l3io-pm:** bound persistent_facts to explicit paths ([82b09c3](https://github.com/ravensorb/bmad-extensions/commit/82b09c3f0a5d761c9495f588c7c5d2f091932f23))
* **l3io-pm:** consult the state and metrics contracts on demand ([70b20f6](https://github.com/ravensorb/bmad-extensions/commit/70b20f6acadd335e6ee1c741987ed79779010d1d))


### Refactoring

* **l3io-pm:** make step-01 the single source of phase gating ([80b64f6](https://github.com/ravensorb/bmad-extensions/commit/80b64f6732bc4e836a29ff7dd354704a760b58ad))


### Documentation

* add a routing table to the digest, and correct the skip_phases claim ([b636230](https://github.com/ravensorb/bmad-extensions/commit/b636230883343755d22e6b4ba24e180b9e56aa17))
* add design spec for subagent context trimming ([274f98d](https://github.com/ravensorb/bmad-extensions/commit/274f98d59cd3745fe2f69d8d1dc8635c142d9dbc))
* add implementation plan for phase gating unification ([977e86b](https://github.com/ravensorb/bmad-extensions/commit/977e86b8fe7cf418a1d602ba530e2baa8c46d056))
* add implementation plan for subagent context trimming ([7d8d129](https://github.com/ravensorb/bmad-extensions/commit/7d8d129cdb7fda1ede7005da4f725bebffd47912))
* **l3io-pm:** describe on-demand reference loading, and record the measurement ([7b9c0ca](https://github.com/ravensorb/bmad-extensions/commit/7b9c0cad3e6f93149ab05ebc9aa3e4fd794fe135))
* **l3io-pm:** describe the parallelism that exists, and fix the verify routing row ([6253c18](https://github.com/ravensorb/bmad-extensions/commit/6253c18994f0f0dbe0c73ddd8564efcbc7f633f7))
* reconcile the remaining gating mirrors and fix-cap references ([0b0af23](https://github.com/ravensorb/bmad-extensions/commit/0b0af23e8cc135f0f106c6db4c3516908c03a570))
* spec phase-gating unification (A) and adaptive parallelism (D) ([b68e4f7](https://github.com/ravensorb/bmad-extensions/commit/b68e4f7afeda29f507b82311728854278be9b5cf))

## [2.1.0](https://github.com/ravensorb/bmad-extensions/compare/2.0.4...2.1.0) (2026-08-17)


### Features

* **l3io-pm:** add plan-aware progress reporting ([54a4421](https://github.com/ravensorb/bmad-extensions/commit/54a442125e38661a48b932e24b581fbccbe948db))


### Refactoring

* **l3io-pm:** remove the unused progress ledger ([4b1ae3c](https://github.com/ravensorb/bmad-extensions/commit/4b1ae3c15e53e02313afaf8bce7123b1196d6b8e))
* **l3io-util:** rename l3io-util-cleanup to l3io-doctor ([cb4aac9](https://github.com/ravensorb/bmad-extensions/commit/cb4aac935dfff57d1a1d887d092db53031681170))


### Documentation

* consolidate upgrade guidance into docs/upgrading.md ([bffc201](https://github.com/ravensorb/bmad-extensions/commit/bffc201c101306787af14a68cbcfbe5b31ccc49f))
* correct the 1.x upgrade path ([45d720a](https://github.com/ravensorb/bmad-extensions/commit/45d720aba306330d7e208de66838661b15c5db9a))
* refresh all documentation for current skills and progress reporting ([5a4d759](https://github.com/ravensorb/bmad-extensions/commit/5a4d759477fc669f65e20ba3e55ed73669c0e838))

## [2.0.4](https://github.com/ravensorb/bmad-extensions/compare/2.0.3...2.0.4) (2026-08-17)


### Fixes

* **l3io-pm:** make the plan snapshot's authority explicit and stop duplicating phases ([b19242a](https://github.com/ravensorb/bmad-extensions/commit/b19242af20c8323377a8861885a2653b821c1358))

## [2.0.3](https://github.com/ravensorb/bmad-extensions/compare/2.0.2...2.0.3) (2026-08-17)


### Fixes

* **l3io-pm:** guard execute against stale plans instead of corrupting epic state ([9a9eb22](https://github.com/ravensorb/bmad-extensions/commit/9a9eb22a858349c45b0dcc67c0bb81527775e3c8))

## [2.0.2](https://github.com/ravensorb/bmad-extensions/compare/2.0.1...2.0.2) (2026-08-16)


### Features

* **l3io-pm:** add calibration file I/O and calibration show ([30be97e](https://github.com/ravensorb/bmad-extensions/commit/30be97e2b33de75fd800aa0f5c193d6a37dad441))
* **l3io-pm:** add estimate-rollup and bump pm-status.py to 2.1.0 ([a853dd6](https://github.com/ravensorb/bmad-extensions/commit/a853dd66fea08b6f1e1505ea03cbf99efaa18cd1))
* **l3io-pm:** add estimate-story ([6d6506f](https://github.com/ravensorb/bmad-extensions/commit/6d6506f10955f076392b6321669fb21e7732f4c9))
* **l3io-pm:** derive closure calibration samples ([50d9c5e](https://github.com/ravensorb/bmad-extensions/commit/50d9c5edbbcedab113326c4528645acc112b9854))
* **l3io-pm:** derive story calibration samples ([06252d8](https://github.com/ravensorb/bmad-extensions/commit/06252d8729df92c8d984f4a7cbb77830e54a11a5))
* **l3io-pm:** emit calibration samples from set-actual ([ddada55](https://github.com/ravensorb/bmad-extensions/commit/ddada558dbc98e29c3a77f74472e1eff0cc1aed7))
* **l3io-pm:** record fix_factor and scope_ratio on estimates ([e50f72e](https://github.com/ravensorb/bmad-extensions/commit/e50f72e1236edc99fa70e03b3a13ec60b3ae39bc))


### Fixes

* **infra:** resolve config through BMad core instead of a file BMad never creates ([ab1145c](https://github.com/ravensorb/bmad-extensions/commit/ab1145c7ffe2cf44ceec66430096725c39e28095))
* **l3io-pm:** correct the calibration loop so it converges to truth ([25b0e38](https://github.com/ravensorb/bmad-extensions/commit/25b0e38361517c4681c1613a476b7a4d5333ae74))
* **l3io-pm:** elaborate stories in place instead of spawning bmad-create-story ([496d6e9](https://github.com/ravensorb/bmad-extensions/commit/496d6e92ae59679d400157da1e40a803b6195f66))
* **l3io-pm:** parse $-prefixed cost before the numeric guard ([7039104](https://github.com/ravensorb/bmad-extensions/commit/7039104b835739e73f6e3b387966329e226c8b72))


### Documentation

* add calibration mechanization design spec ([7e55f48](https://github.com/ravensorb/bmad-extensions/commit/7e55f4868a121b8fa7e5fc767cdf9b45508013df))
* add calibration mechanization implementation plan (8 tasks) ([db71380](https://github.com/ravensorb/bmad-extensions/commit/db7138072d3c09e321f0e7833a645bdb55b72dfd))
* bring architecture.md and l3io-pm-reference.md up to the current design ([826a7a8](https://github.com/ravensorb/bmad-extensions/commit/826a7a887dade85fa1eb6d4a3d1aef704cafaef6))
* **l3io-pm:** complete the dependency table and record declared-vs-invoked gaps ([f517d0b](https://github.com/ravensorb/bmad-extensions/commit/f517d0b9ca150afe682f43bda8362f040449a3bb))
* **l3io-pm:** correct the QA row — no QA phase is actually invoked ([d26c528](https://github.com/ravensorb/bmad-extensions/commit/d26c5281d376636d016b2b72d274f363ea1db2ae))
* **l3io-pm:** document the calibration loop that now runs ([cabc4ab](https://github.com/ravensorb/bmad-extensions/commit/cabc4abbc4939d5ad8884c8944a4042c34d83642))
* **l3io-pm:** fix false fix-factor claim in calibration worked example ([d1d0978](https://github.com/ravensorb/bmad-extensions/commit/d1d097848adcbe6446e27c86fdf047b5e43c83ae))
* **l3io-pm:** fix two stale references surfaced during the create-story review ([25ee2e4](https://github.com/ravensorb/bmad-extensions/commit/25ee2e462846d41f43c08b925eae7dcb7328181f))

## [2.0.1](https://github.com/ravensorb/bmad-extensions/compare/2.0.0...2.0.1) (2026-08-16)


### Features

* **l3io-pm:** add list-issues subcommand to pm-status.py ([d6fd339](https://github.com/ravensorb/bmad-extensions/commit/d6fd33923d79c6f802730cad49e50c2ecdc5d5c4))
* **l3io-pm:** resolve state nodes by key over a sharded tree ([f3f7c2d](https://github.com/ravensorb/bmad-extensions/commit/f3f7c2d6e6ae08ffe2da5fe928f0b91f57b61e92))


### Fixes

* **ci-cd:** update test path to skills/_shared/ for v2 flat layout ([4f435fb](https://github.com/ravensorb/bmad-extensions/commit/4f435fb038c6ed2b48af9f12c285cb3b6bd48f4e))
* **infra:** document the sharded layout and gate releases on script sync ([d6c5ef3](https://github.com/ravensorb/bmad-extensions/commit/d6c5ef3125b156e838154e87ca0b6896062b1dd9))
* **l3io-pm:** bind {runtime} at activation for set-actual/verify calls ([3b67541](https://github.com/ravensorb/bmad-extensions/commit/3b67541feff4f3a3b3fd9c23c176c39671b5c3a0))
* **l3io-pm:** call pm-status.py with keys, and fix the upgrade deadlock ([91ea8e1](https://github.com/ravensorb/bmad-extensions/commit/91ea8e165472fe587a14439be60d46c804d3b16d))
* **l3io-pm:** close upgrade-path gaps in migration, help, and state helper ([6186129](https://github.com/ravensorb/bmad-extensions/commit/61861295373370a2a04ae2014d73c1b062eb3aa1))
* **l3io-pm:** gate module setup on state being version-controlled ([0555dc9](https://github.com/ravensorb/bmad-extensions/commit/0555dc9346b2eecebc222a44103b34f84cc979de))
* **l3io-pm:** read the sharded layout in l3io-help ([a686ca2](https://github.com/ravensorb/bmad-extensions/commit/a686ca2acfcbbf163da60b46de443d8b167c32e7))
* **l3io-pm:** remove dead deferred epic-status bucket from l3io-plan ([16338b5](https://github.com/ravensorb/bmad-extensions/commit/16338b5182ecd5c15feddb3987c659a1eb2b0851))
* **l3io-pm:** repair l3io-sync against its real script CLIs ([a1e9645](https://github.com/ravensorb/bmad-extensions/commit/a1e96457e6799ff467ab369e759b76879159149d))
* **l3io-util:** extend clean-legacy to cover migrate-state's actual backups ([ca549a0](https://github.com/ravensorb/bmad-extensions/commit/ca549a0c08c348c56266475a86d943568c411373))
* **l3io-util:** migrate to the sharded layout, verify before destroying ([9da8e61](https://github.com/ravensorb/bmad-extensions/commit/9da8e61882da4500f26ff22ea298f4d9cbb8ebbd))


### Documentation

* add design spec and implementation plan for state relocation ([9a9dc4f](https://github.com/ravensorb/bmad-extensions/commit/9a9dc4fcd0edd6f03090e3b1b1eb4ea1702b66cf))
* **l3io-pm:** add metrics-contract.md reference and wire into shared sync ([83ca5d0](https://github.com/ravensorb/bmad-extensions/commit/83ca5d07068c408cec2c41a8ff7345f936000bfc))
* **l3io-pm:** correct stale pm-status.py help text ([1f8378e](https://github.com/ravensorb/bmad-extensions/commit/1f8378ebd43766ea8eda4b9597e2209d3025e1d7))
* **l3io-pm:** rewrite status-files.md as the state layout contract ([f61cb20](https://github.com/ravensorb/bmad-extensions/commit/f61cb20750b4f828824b93c601ff0648f2c4c1d2))

## [2.0.0](https://github.com/ravensorb/bmad-extensions/compare/1.1.1...2.0.0) (2026-08-15)


### Features

* **infra:** add pm-status.py v2.0.0 with lock, field, issue, and archive subcommands ([f9c71fb](https://github.com/ravensorb/bmad-extensions/commit/f9c71fbb7cadd9019126b064878d000633c82faa))
* **infra:** add resolve_config.py and memlog.py runtime scripts ([c1ad12a](https://github.com/ravensorb/bmad-extensions/commit/c1ad12a21798671564011bb1c8d141d362b5993e))
* **infra:** add shared step files for all PM skill categories ([9f7e98a](https://github.com/ravensorb/bmad-extensions/commit/9f7e98a20ece6976d063384ff44515058c898d74))
* **infra:** add updated status-files.md for _bmad/state/ layout ([c7cb6d4](https://github.com/ravensorb/bmad-extensions/commit/c7cb6d4b0fede8827690155334c5d5b5d4b7f17e))
* **infra:** rewrite sync-shared-scripts.mjs for skills/ flat layout and new script manifest ([0a937e7](https://github.com/ravensorb/bmad-extensions/commit/0a937e745bdad6f1aeb1751b1c5c7b5cbabad151))
* **l3io-pm:** add l3io-execute skill (merged sprint+epic execution) ([398c035](https://github.com/ravensorb/bmad-extensions/commit/398c035184c5bc225ddb1f59b6784509edf049af))
* **l3io-pm:** add l3io-help skill (state snapshot + next-action recommendation) ([37dc941](https://github.com/ravensorb/bmad-extensions/commit/37dc94196a3e11a075141073da878b61bb311934))
* **l3io-pm:** add l3io-plan skill (renamed from plan-execution, steps architecture) ([f0b367b](https://github.com/ravensorb/bmad-extensions/commit/f0b367b0bf620dcd2a9d562300fb011cf625b2d7))
* **l3io-pm:** add l3io-sync skill (GitHub Issues bidirectional sync) ([f9bb7fa](https://github.com/ravensorb/bmad-extensions/commit/f9bb7fac0341e39d4d8838b8fac0c7054b769202))
* **l3io-sec:** rename l3io-sec-agent-redteam → l3io-sec-redteam (flat layout) ([35a176b](https://github.com/ravensorb/bmad-extensions/commit/35a176b98c8c28a359ce0ceff55d149e63de51da))
* **l3io-util:** add migrate-state mode and 9-check health check to util-cleanup ([c672741](https://github.com/ravensorb/bmad-extensions/commit/c672741bb7654f5f70d61befe4efc0ac890b32ae))


### Fixes

* **infra:** patch brace-expansion DoS vulnerability in lockfile ([6e5d4ab](https://github.com/ravensorb/bmad-extensions/commit/6e5d4ab047ddfd45f5eb3a879863294b643ed0a7))
* **infra:** rename {ava_key} → {story_key} in sync step-04-resolve.md ([81ced51](https://github.com/ravensorb/bmad-extensions/commit/81ced518be8de3e8cc44846d760e486dc990db60))
* **infra:** update stale sprint-execute/epic-execute refs in CLAUDE.md to l3io-execute ([c071e51](https://github.com/ravensorb/bmad-extensions/commit/c071e51f3426762f0fc02a8b054061e8e5b1bafa))
* **infra:** use key: schema in primary SAMPLE fixture for pm-status tests ([f8f9fda](https://github.com/ravensorb/bmad-extensions/commit/f8f9fdaf0a30a828fe1e0eafe4a17c4e8dc5a958))
* **l3io-pm:** remove ADO reference from sync module-help.csv description ([83bbabc](https://github.com/ravensorb/bmad-extensions/commit/83bbabcf732007c62761f61fd8f8b4c3c758e80f))
* **l3io-sec:** correct SKILL_NAME in init-sanctum.py (remove bmad- prefix) ([8532d09](https://github.com/ravensorb/bmad-extensions/commit/8532d09490def28abe72d307ee3ad2e1235f6e2d))


### Documentation

* add v2.0.0 migration design spec ([552a313](https://github.com/ravensorb/bmad-extensions/commit/552a313888a615c564331846f27d364b2a4a9186))
* add v2.0.0 migration implementation plan (14 tasks) ([8fd0e51](https://github.com/ravensorb/bmad-extensions/commit/8fd0e514dbd255fe83687e1609a374064fb3190f))
* complete v2.0.0 design spec with full gap analysis ([0f4f307](https://github.com/ravensorb/bmad-extensions/commit/0f4f307cec4a479f8e3cedd335f41d2aa99eb32a))
* show full tools list in upgrade command ([809258b](https://github.com/ravensorb/bmad-extensions/commit/809258bc97008aaaa773fc18cdea87dad267f070))
* simplify upgrade to a single explicit one-liner with no prompts ([e3945c5](https://github.com/ravensorb/bmad-extensions/commit/e3945c5661486d279a057e0bbee3ad4f1de8afc1))
* simplify upgrade to quick-update one-liner ([f85c705](https://github.com/ravensorb/bmad-extensions/commit/f85c705d2d54745c04ef7086bf0d86e12f7bf1c9))
* update migration plan with post-2.0.0 fixes from reference (2.0.1-2.0.4) ([32a9f92](https://github.com/ravensorb/bmad-extensions/commit/32a9f922d0159f80d3a9688d5cb6a91db80872aa))


### Maintenance

* **infra:** update symlinks, marketplace.json, and CLAUDE.md for flat skills/ layout ([598a7ce](https://github.com/ravensorb/bmad-extensions/commit/598a7ce418c38dcee9586edfd0363df7f8d6ea5c))
* **l3io-arch:** move l3io-arch-review to flat skills/ layout ([fc8506e](https://github.com/ravensorb/bmad-extensions/commit/fc8506ea132edd9a5ef4c363bfbd104334c7ccc7))
* remove src/ — all skills migrated to flat skills/ layout ([a114550](https://github.com/ravensorb/bmad-extensions/commit/a114550d0f937925149ac67ea977f92140864e22))

## [1.1.1](https://github.com/ravensorb/bmad-extensions/compare/1.1.0...1.1.1) (2026-07-31)


### Features

* **infra,l3io-pm:** move _shared/ to repo-level src/_shared/ and align with the reference implementation ([800118c](https://github.com/ravensorb/bmad-extensions/commit/800118c639bf3657285f7fb2fc396a755f76fec9))

## [1.1.0](https://github.com/ravensorb/bmad-extensions/compare/1.0.28...1.1.0) (2026-07-31)

## [1.0.28](https://github.com/ravensorb/bmad-extensions/compare/1.0.27...1.0.28) (2026-07-31)


### Features

* **l3io-pm,l3io-arch:** pre-execution epic arch gate + story technical-AC gate ([16034a9](https://github.com/ravensorb/bmad-extensions/commit/16034a9739c8bb04efe0628b92287e47a865e706))
* **l3io-pm:** add shared atomic pm-status.py status/progress helper ([f83c67b](https://github.com/ravensorb/bmad-extensions/commit/f83c67be9e168f6379341bef02a4d1e708c89045))
* **l3io-pm:** route status/actuals/progress through pm-status.py; auto parallelism ([32be2f5](https://github.com/ravensorb/bmad-extensions/commit/32be2f509da41df2771425c63c0030c509c490ef))


### Fixes

* **l3io-pm:** harden token/cost capture across nested subagent runs ([a42c1ae](https://github.com/ravensorb/bmad-extensions/commit/a42c1ae1455729a540893a55a8996f9b5fd5291d))


### Documentation

* **l3io-pm:** document reliability/quality changes and shared-helper model ([3d1b65d](https://github.com/ravensorb/bmad-extensions/commit/3d1b65deea0d34e03b199c0e82805377837afd11))

## [1.0.27](https://github.com/ravensorb/bmad-extensions/compare/1.0.26...1.0.27) (2026-07-08)


### Features

* **l3io-arch:** add architecture standards module ([71a3f49](https://github.com/ravensorb/bmad-extensions/commit/71a3f498f770817da83ab58d12db0ef11174bf8c))
* **l3io-pm:** add optional ATDD scaffold phase to sprint story loop ([1ede67e](https://github.com/ravensorb/bmad-extensions/commit/1ede67e0e9bc13856c9dfd740911c87025d7ef10))


### Documentation

* cover both Claude Code and GitHub Copilot in install/upgrade ([06e8055](https://github.com/ravensorb/bmad-extensions/commit/06e8055d47b3e25f8ccb93897f5246bf6745a99c))
* drop folded-in *-setup skills from Modules table ([ec65e20](https://github.com/ravensorb/bmad-extensions/commit/ec65e20488528f3f1ba6e91e64d13f736024e3a9))
* **l3io-arch:** document new module and fix stale module docs ([d51a8bd](https://github.com/ravensorb/bmad-extensions/commit/d51a8bd330c2b90635717911f53924991f00516f))
* **l3io-sec:** name GitHub Copilot explicitly in module.yaml discovery note ([9f7382c](https://github.com/ravensorb/bmad-extensions/commit/9f7382c204453755e5a1e15e088ab8f6109211ec))

## [1.0.26](https://github.com/ravensorb/bmad-extensions/compare/1.0.25...1.0.26) (2026-07-05)


### Fixes

* **l3io-pm,l3io-sec,l3io-util:** add top-level module.yaml for installer discovery ([289caf9](https://github.com/ravensorb/bmad-extensions/commit/289caf9fdd43a88ca5638a2e1a7e9df6253bb02d))

## [1.0.25](https://github.com/ravensorb/bmad-extensions/compare/1.0.24...1.0.25) (2026-07-01)


### Refactoring

* embed module setup in operational skills; remove standalone setup skills ([9612a0f](https://github.com/ravensorb/bmad-extensions/commit/9612a0f23f50278255ff14e2ff8aa971f38f8b1c))

## [1.0.24](https://github.com/ravensorb/bmad-extensions/compare/1.0.23...1.0.24) (2026-07-01)


### Features

* **l3io-util:** add help, stats, backlog, normalize, clean-legacy modes; reorganize command structure ([1a32a6f](https://github.com/ravensorb/bmad-extensions/commit/1a32a6fd321aaba0c69e3d7b4e759bd2daf69877))

## [1.0.23](https://github.com/ravensorb/bmad-extensions/compare/1.0.22...1.0.23) (2026-06-29)


### Features

* **l3io-util:** add reconcile-status mode to l3io-util-cleanup ([adc9c32](https://github.com/ravensorb/bmad-extensions/commit/adc9c321a31e6a67ebc7bdef9896ffa8dcb4048e))

## [1.0.22](https://github.com/ravensorb/bmad-extensions/compare/1.0.21...1.0.22) (2026-06-27)


### Features

* **l3io-pm,l3io-util:** redesign backlog item lifecycle and key format ([e898962](https://github.com/ravensorb/bmad-extensions/commit/e898962062f64f841438ceb1b98aec5fb853553f))

## [1.0.21](https://github.com/ravensorb/bmad-extensions/compare/1.0.20...1.0.21) (2026-06-27)


### Features

* **l3io-util:** health-check default mode for l3io-util-cleanup ([94f47cc](https://github.com/ravensorb/bmad-extensions/commit/94f47ccde15e2dd1a0a117ee53ab70174000ba98))


### Documentation

* update README with upgrade section and fix sprint-status naming ([6351c7e](https://github.com/ravensorb/bmad-extensions/commit/6351c7ee122cf003b86105e87c9b2149b1f54104))

## [1.0.20](https://github.com/ravensorb/bmad-extensions/compare/1.0.19...1.0.20) (2026-06-27)


### Features

* **l3io-pm,l3io-util:** rename sprint-status-active.yaml → sprint-status.yaml ([b466dab](https://github.com/ravensorb/bmad-extensions/commit/b466dab386c929a38493cdffbae5bfcc71cd4f90))

## [1.0.19](https://github.com/ravensorb/bmad-extensions/compare/1.0.18...1.0.19) (2026-06-26)


### Features

* **l3io-util:** update-ai-rules mode + migrate-schema split layout + Step 6/7 fixes ([23c696a](https://github.com/ravensorb/bmad-extensions/commit/23c696a2f406141dced32b54d57567d0ab599dfb))

## [1.0.18](https://github.com/ravensorb/bmad-extensions/compare/1.0.17...1.0.18) (2026-06-26)


### Fixes

* **l3io-pm:** consolidate module registry into setup skill to fix sprint install ([0cc116e](https://github.com/ravensorb/bmad-extensions/commit/0cc116e38b5f932067e4737c4abac2ad0175b1cd))

## [1.0.17](https://github.com/ravensorb/bmad-extensions/compare/1.0.16...1.0.17) (2026-06-26)


### Features

* **l3io-pm,l3io-util:** status validation gates + sort-status mode ([c8f541f](https://github.com/ravensorb/bmad-extensions/commit/c8f541fa48fd4331ad25b410cb2082ecaadcc6a1))

## [1.0.16](https://github.com/ravensorb/bmad-extensions/compare/1.0.15...1.0.16) (2026-06-25)


### Features

* **l3io-pm:** bottom-up estimate roll-up + decomposed scope/closure/fix calibration ([7c5ab2f](https://github.com/ravensorb/bmad-extensions/commit/7c5ab2f7fc8ad9df79820e3bbdc2f4b888603416))

## [1.0.15](https://github.com/ravensorb/bmad-extensions/compare/1.0.14...1.0.15) (2026-06-25)


### Fixes

* **l3io-pm,l3io-sec,l3io-util:** rename module-help.csv header after,before to preceded-by,followed-by ([1b0851e](https://github.com/ravensorb/bmad-extensions/commit/1b0851eabf6e42ea8b9dec83b685fe56012355ae))

## [1.0.14](https://github.com/ravensorb/bmad-extensions/compare/1.0.13...1.0.14) (2026-06-25)


### Features

* **l3io-pm,l3io-sec,l3io-util:** rename skills to l3io-* prefix; scaffold setup skills; wire first-run auto-config ([6051048](https://github.com/ravensorb/bmad-extensions/commit/6051048ca602d2a88abb863390407a7697131887))

## [1.0.13](https://github.com/ravensorb/bmad-extensions/compare/1.0.12...1.0.13) (2026-06-25)


### Fixes

* **l3io-pm,l3io-util:** fix dedupe contract, announce counts, and loop header clarity ([6e10f44](https://github.com/ravensorb/bmad-extensions/commit/6e10f4487b17fe2ad393e835821aef63db849406))

## [1.0.12](https://github.com/ravensorb/bmad-extensions/compare/1.0.11...1.0.12) (2026-06-22)


### Features

* **l3io-pm:** leanness cut-list + bmad-defer harvest in sprint closure ([d6a8183](https://github.com/ravensorb/bmad-extensions/commit/d6a8183a74fe8b78bb5a262a0d8686f4f2f54755))
* **l3io-util:** add harvest-debt mode for bmad-defer code markers ([9f2c07b](https://github.com/ravensorb/bmad-extensions/commit/9f2c07b4d6eda619e950ded04bbd48a6a39f59e9))


### Documentation

* **l3io-pm:** align reference + getting-started with 1.0.9–1.0.11 features ([bcce91e](https://github.com/ravensorb/bmad-extensions/commit/bcce91e5e8a50b82b361d2fe165173a09fb923be))

## [1.0.11](https://github.com/ravensorb/bmad-extensions/compare/1.0.10...1.0.11) (2026-06-15)


### Features

* **l3io-pm:** split sprint-status.yaml into active/backlog/archived state files ([eb879ef](https://github.com/ravensorb/bmad-extensions/commit/eb879ef7cb1ab4981daf98cf1c968280291b134f))


### Fixes

* **l3io-pm:** scope token/cost capture by session id, not cwd ([5b9ea56](https://github.com/ravensorb/bmad-extensions/commit/5b9ea560225d0d11d3b3982b5aede2d4fef3a7dc))


### Maintenance

* **infra:** align commit scope list with actual module scopes ([98feb0c](https://github.com/ravensorb/bmad-extensions/commit/98feb0c3381226f417fc47ae88a8847ad0e708d5))

## [1.0.10](https://github.com/ravensorb/bmad-extensions/compare/1.0.9...1.0.10) (2026-06-13)


### Features

* **l3io-pm:** enforce estimates + actuals hard rule with runtime-aware metric capture ([57236d3](https://github.com/ravensorb/bmad-extensions/commit/57236d3999273aaa408c68b38f75aaba49ade511))

## [1.0.9](https://github.com/ravensorb/bmad-extensions/compare/1.0.8...1.0.9) (2026-05-28)


### Features

* **l3io-pm:** add estimation calibration from plan-vs-actual sprint history ([cf5ec00](https://github.com/ravensorb/bmad-extensions/commit/cf5ec00643deb454ea5488479b0b51dd0eca130b))

## [1.0.8](https://github.com/ravensorb/bmad-extensions/compare/1.0.7...1.0.8) (2026-05-28)


### Fixes

* **infra:** stage sync output files in postbump so release picks them up ([27a90b6](https://github.com/ravensorb/bmad-extensions/commit/27a90b6bc7416cb4d79a94c4affdb50f34520edf))


### Documentation

* **l3io-pm:** update reference and getting-started for new schema and migrate-schema ([9a328dc](https://github.com/ravensorb/bmad-extensions/commit/9a328dcec6fd06a67ae99d95d93bf678579900ad))


### Maintenance

* merge remote 1.0.6 release branch into local history ([45399eb](https://github.com/ravensorb/bmad-extensions/commit/45399eb23b79fc28c8e62889f7b95f4e3c32e8a5))
* **release:** 1.0.6 ([5d1b7c5](https://github.com/ravensorb/bmad-extensions/commit/5d1b7c56c45c57a0dec27e62e5a835340ae43256))

## [1.0.7](https://github.com/ravensorb/bmad-extensions/compare/1.0.5...1.0.7) (2026-05-28)


### Features

* **l3io-pm:** enrich sprint-status.yaml schema with estimates, actuals, and classification tracking ([abb7390](https://github.com/ravensorb/bmad-extensions/commit/abb7390943e783b98b0407ef5c9a8561f6b859c7))
* **l3io-util:** add migrate-schema mode to bmad-l3io-util-cleanup ([a93e8d8](https://github.com/ravensorb/bmad-extensions/commit/a93e8d8f2c28bfe11c258554a9bded1a9c3c79a8))


### Fixes

* **custom:** align module-help.csv headers with canonical schema ([6284eeb](https://github.com/ravensorb/bmad-extensions/commit/6284eeb08cdf083030dd95aa7f2ec4bf0c683243))


### Maintenance

* fix postbump hook and sync marketplace versions to 1.0.6 ([a74c216](https://github.com/ravensorb/bmad-extensions/commit/a74c2166e8bb662123a9cd637ff05cb148458e3c))
* **release:** 1.0.6 ([2d98fde](https://github.com/ravensorb/bmad-extensions/commit/2d98fde4dea8a902ae6b1356ee0cc4c764868d7a))

## [1.0.6](https://github.com/ravensorb/bmad-extensions/compare/1.0.5...1.0.6) (2026-05-27)


### Features

* **l3io-pm:** enrich sprint-status.yaml schema with estimates, actuals, and classification tracking ([35eb644](https://github.com/ravensorb/bmad-extensions/commit/35eb64478ec09947517acb24450b0ed5de8eca4c))

## [1.0.5](https://github.com/ravensorb/bmad-extensions/compare/1.0.4...1.0.5) (2026-05-27)


### Fixes

* **l3io-pm:** detect redteam skill in .claude/skills as well as .claude/commands ([7f9c93f](https://github.com/ravensorb/bmad-extensions/commit/7f9c93f157ccb6d9590e12be4996d2461fbd8ebc))

## [1.0.4](https://github.com/ravensorb/bmad-extensions/compare/1.0.3...1.0.4) (2026-05-25)


### Features

* **l3io-pm:** add cicd-guidelines reference with multi-runner pipeline conventions ([85a409f](https://github.com/ravensorb/bmad-extensions/commit/85a409f68a8adc7d9b55df1044ef4fdc0dd25cf4))
* **l3io-pm:** add cost estimates at story, sprint, and epic level ([5a64af9](https://github.com/ravensorb/bmad-extensions/commit/5a64af9f207807c25f904fb600ec1e16da17672c))
* **l3io-pm:** propagate deferred-cleanup instruction to all subagent prompts ([7318c63](https://github.com/ravensorb/bmad-extensions/commit/7318c63180b7e663593d49495e5dc562e55ef78f))

## [1.0.3](https://github.com/ravensorb/bmad-extensions/compare/1.0.2...1.0.3) (2026-05-17)


### Features

* **l3io-pm:** add epic backlog file accumulation to sprint closure ([2e7da85](https://github.com/ravensorb/bmad-extensions/commit/2e7da856269e27577f4f96545238acd4e025a601))
* **l3io-pm:** add optional deferred file cleanup to batch rm at sprint/epic close ([a630713](https://github.com/ravensorb/bmad-extensions/commit/a630713393c93f50c96390d2db520b5258789534))
* **l3io-util:** enhance cleanup with recursive scan, deferred work tracking, and completeness loop ([9ddda11](https://github.com/ravensorb/bmad-extensions/commit/9ddda115b32b31e11f9377c78408d33f3476af1f)), closes [#5](https://github.com/ravensorb/bmad-extensions/issues/5)


### Maintenance

* bump all module versions to 1.0.3 ([30ec22b](https://github.com/ravensorb/bmad-extensions/commit/30ec22b35d9f04b9d77447c4617c0ba236bcc928))

## 1.0.2 (2026-05-16)

### Features

* **l3io-pm**: cut interactive prompts during sprint and epic execution. The orchestrators now run end-to-end with minimal user intervention; the only remaining interactive prompt in normal flow is the sprint scope confirmation when a sprint is launched **manually** (sprints spawned by epic-execute run headlessly with no confirmation).

### Behavior changes

* **Per-story fix loop cap raised from 3 → 10 iterations.** Loop runs fix → QA → re-check autonomously; only halts and prompts `{user_name}` if 10 iterations still leave issues unresolved.
* **Quality gate now includes Medium severity.** Sprint and epic closure require all Critical, High, and Medium findings to be resolved (previously: Critical + High only). Low findings auto-defer to backlog with no prompt.
* **Closure fix loop added** (sprint and epic): same 10-iteration cap. Findings are auto-triaged to fix-now (Critical/High/Medium + undocumented drift + functional AC gaps) vs. defer-to-backlog (Low) and processed without per-item user prompts.
* **Removed prompts:** per-story prep checkpoint, between-sprint pause in epic execution, UX-spec-not-found ask (now auto-SKIP when no UX specs are found).
* **HALT prompts now include estimates** (time + tokens per option) so `{user_name}` can decide informed when the 10-iteration cap is hit.

## 1.0.1 (2026-05-16)

### Fixes

* **install:** silence `collectAgentsFromModuleYaml` and `writeCentralConfig` warnings during install by restructuring to the canonical BMad community module layout — `src/<module>/module.yaml` + `src/<module>/module-help.csv` at each module root, with skills nested as `src/<module>/bmad-l3io-<skill>/`. Agents declared in `module.yaml` now register correctly in the consumer's `config.toml` and user-scoped prompt keys file to `config.user.toml` as intended.

### Refactoring

* **infra:** rename all skills with `bmad-` prefix (SKILL-04 compliance): `bmad-l3io-pm-sprint-execute`, `bmad-l3io-pm-epic-execute`, `bmad-l3io-sec-agent-redteam`, `bmad-l3io-util-cleanup`. Slash commands change accordingly (`/bmad-l3io-pm-sprint-execute`, etc.).
* **infra:** move from flat `skills/` layout to per-module `src/<module>/` subtrees so PluginResolver Strategy 1 (root module files) fires cleanly for each plugin.
* **l3io-sec:** strip `name:` / `description:` frontmatter from `references/*.md` files (bmad-method validator rules WF-01/WF-02 reserve those fields for `SKILL.md` only). `CAPABILITIES.md` is now populated from the hand-curated `assets/CAPABILITIES-template.md` instead of being auto-generated from reference frontmatter.

### Notes

* Slash command names change from `/l3io-*` to `/bmad-l3io-*` — re-install in consumer repos picks up the new symlinks.
* Module names (`l3io-pm`, `l3io-sec`, `l3io-util`) and module codes are unchanged.

## 1.0.0 (2026-05-16)

Initial release of `bmad-l3io-extensions` — three installable BMad community modules for sprint/epic delivery, security review, and artifact organization.

### Features

* **l3io-pm**: sprint and epic execution orchestration
  * `bmad-l3io-pm-sprint-execute`: per-story prep → dev → code review → QA → fix loop, then closure (retro, clean release, adversarial, red team, UX, arch drift, issue triage). Sprint cannot close until all Critical/High findings are resolved.
  * `bmad-l3io-pm-epic-execute`: sprint grouping → sprint execution loop → epic-level closure (retro, parallel review batch, arch drift, functional completeness, issue triage). Epic cannot close until all Critical/High findings and undocumented drift are resolved.
* **l3io-sec**: memory-backed red team security agent (`bmad-l3io-sec-agent-redteam`) — adversarial review across five threat lenses (EXT, INS, CHA, ABU, DAR) with an AI poisoning cross-cut (AIP) and live cloud/platform best practices research (PBR). Persists a per-project sanctum with research cache.
* **l3io-util**: one-time artifact migration utility (`bmad-l3io-util-cleanup`) that reorganizes flat BMad artifacts into the standard `epic-XX/sprint-YY` folder layout with zero-padded names and reference reconciliation.

### Execution model

* Each phase runs in a fresh subagent — all state passes through disk, never through in-memory hand-off.
* Adaptive parallelism: defaults to sequential, hard cap of 4 concurrent subagents when independence and state safety can be verified.
* Quality gates: sprint and epic closure require all Critical and High severity findings to be resolved.
