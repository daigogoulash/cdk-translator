import json
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_iam as iam,
    aws_stepfunctions as sf,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct

class TranslatorStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # S3 bucket for audio files
        audio_bucket = s3.Bucket(self, "AudioBucket")

        # IAM role for Step Functions
        role = iam.Role(self, "StateMachineRole",
                        assumed_by=iam.ServicePrincipal("states.amazonaws.com"))

        role.add_to_policy(iam.PolicyStatement(
            resources=["*"],
            actions=[
                "s3:*",
                "transcribe:*",
                "translate:*",
                "polly:*",
                "comprehend:*",
            ]
        ))

        # Load the state machine definition JSON and replace placeholders with actual bucket names
        with open('assets/state_machine.json', 'r') as f:
            state_machine_definition = json.load(f)

        # Replace placeholders
        state_machine_definition_str = json.dumps(state_machine_definition)
        state_machine_definition_str = state_machine_definition_str.replace('{{AUDIO_BUCKET}}', audio_bucket.bucket_name)
        state_machine_definition = json.loads(state_machine_definition_str)

        # Create the state machine definition
        state_machine_definition_body = sf.DefinitionBody.from_string(json.dumps(state_machine_definition))

        # State machine definition from the modified JSON
        state_machine = sf.StateMachine(
            self, "StateMachine",
            state_machine_name="AudioTranslation",
            definition_body=state_machine_definition_body,
            role=role
        )

        # Event rule to trigger the state machine on S3 object creation
        rule = events.Rule(self, "Rule",
                           event_pattern=events.EventPattern(
                               source=["aws.s3"],
                               detail_type=["Object Created"],
                               resources=[audio_bucket.bucket_arn],
                               detail={
                                   "eventName": ["PutObject", "CompleteMultipartUpload"]
                               }
                           ))

        rule.add_target(targets.SfnStateMachine(state_machine))
