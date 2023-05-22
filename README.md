# nightly uplolad. 


This provides a standard GitHub Action to upload nightly builds to the
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


To request access to the repository please open an issue on [this action
repository](https://github.com/scientific-python/upload-nightly-action). You can
then generate a token at `https://anaconda.org/<username>/settings/access`, check
minimum permissions and add the token as a secret to your GitHub repository.


# using nightly builds in CI. 

To test those nightly build, you can use the following command to install from
the nightly package. 

```
python -m pip install matplotlib -i https://pypi.org/simple  -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple  --upgrade --pre
```

Note that second `-i` parameter will take priority, it needs to come second if
you want to pull from nightly otherwise it will pull from pypi. 

```
if package in nightly:
   try to install from nightly
else:
   try to install from pypi
```
