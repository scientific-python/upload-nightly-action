# upload-nightly-action Maintainer Notes

## Grype security scans in CI

[`grype`](https://github.com/anchore/grype) is used to perform scheduled security scans of the `upload-nightly-action` Pixi environment in CI.
In the event that the scan fails, a maintainer should:

1. Check to see if the detected vulnerability can be avoided by upgrading dependencies with

```
pixi upgrade
```

2. If the `pixi.lock` has been updated by this action, then the offending packages should be checked for updates with `pixi list` and the `grype` scan should be repeated with

```
pixi run grype
```

3. If the `pixi.lock` lock file is not updated, then the changes to the `pixi.toml` Pixi manifest can be ignored/reverted and a maintainer should open up a tracking GitHub issue that reports the vulnerability and summarizes their understanding of the root cause of the vulnerability being introduced to the environment.
`pixi tree --invert` may help with this.

Example:

```
pixi tree --invert openssl
```
