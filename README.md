# nightly uplolad. 


This provide a standard action to upload nightly updates to the
scientific-python nightly channel. 

In your Continuous Intregration pipeline once you've built you wheel, you can
use the following snippet to upload to our central nightly repository:


```yml
jobs:
  steps:
    ...
    - name: Upload wheel
      uses: scientific-python/upload-nightly-action@main
      with:
        artifacts_path: dist
        anaconda_nightly_upload_token: ${{secrets.UPLOAD_TOKEN}}
```


To request access to the repository please open and issue on [this action
repository](https://github.com/scientific-python/upload-nightly-action), you can
generate a token at `https://anaconda.org/<username>/settings/access` ... chck
minimum permissions and set it in github tokens secrets. 

