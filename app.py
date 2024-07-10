#!/usr/bin/env python3
import os
import aws_cdk as cdk
from translator_aws.translator_aws_stack import TranslatorStack

app = cdk.App()
TranslatorStack(app, "TranslatorStack")
app.synth()
