from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_iam as iam,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
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
        state_machine_role = iam.Role(self, "StateMachineRole",
                                      assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
                                      managed_policies=[
                                          iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                                          iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess"),
                                          iam.ManagedPolicy.from_aws_managed_policy_name("AmazonTranscribeFullAccess"),
                                          iam.ManagedPolicy.from_aws_managed_policy_name("ComprehendReadOnly"),
                                          iam.ManagedPolicy.from_aws_managed_policy_name("TranslateReadOnly"),
                                          iam.ManagedPolicy.from_aws_managed_policy_name("AmazonPollyFullAccess")
                                      ])

        # Step Function definition
        transcribe_task = tasks.CallAwsService(self, "TranscribeAudio",
                                               service="transcribe",
                                               action="startTranscriptionJob",
                                               parameters={
                                                   "TranscriptionJobName": sfn.JsonPath.string_at("$.filename"),
                                                   "LanguageCode": "auto",
                                                   "Media": {
                                                       "MediaFileUri": sfn.JsonPath.string_at("$.s3_input_audio_file")
                                                   },
                                                   "OutputBucketName": audio_bucket.bucket_name,
                                                   "OutputKey": "transcription_output/"
                                               },
                                               iam_resources=["*"],
                                               result_path="$.transcription_result")

        detect_language_task = tasks.CallAwsService(self, "DetectLanguage",
                                                    service="comprehend",
                                                    action="detectDominantLanguage",
                                                    parameters={
                                                        "Text": sfn.JsonPath.string_at("$.transcription_text.Body.results.transcripts[0].transcript")
                                                    },
                                                    iam_resources=["*"],
                                                    result_path="$.language_detection_result")

        translate_text_task = tasks.CallAwsService(self, "TranslateText",
                                                   service="translate",
                                                   action="translateText",
                                                   parameters={
                                                       "Text": sfn.JsonPath.string_at("$.transcription"),
                                                       "SourceLanguageCode": sfn.JsonPath.string_at("$.language_detection_result.Languages[0].LanguageCode"),
                                                       "TargetLanguageCode": "en"
                                                   },
                                                   iam_resources=["*"],
                                                   result_path="$.translation_result")

        synthesize_speech_task = tasks.CallAwsService(self, "GenerateAudio",
                                                      service="polly",
                                                      action="startSpeechSynthesisTask",
                                                      parameters={
                                                          "Text": sfn.JsonPath.string_at("$.translation_result.TranslatedText"),
                                                          "OutputFormat": "mp3",
                                                          "VoiceId": "Joanna",
                                                          "OutputS3BucketName": audio_bucket.bucket_name,
                                                      },
                                                      iam_resources=["*"],
                                                      result_path="$.polly_result")

        definition = transcribe_task.next(detect_language_task).next(translate_text_task).next(synthesize_speech_task)

        state_machine = sfn.StateMachine(self, "StateMachine",
                                         definition=definition,
                                         role=state_machine_role)

        # EventBridge rule to trigger Step Function on audio file upload
        event_rule = events.Rule(self, "AudioUploadRule",
                                 event_pattern={
                                     "source": ["aws.s3"],
                                     "detail": {
                                         "bucket": {
                                             "name": [audio_bucket.bucket_name]
                                         },
                                         "object": {
                                             "key": [{
                                                 "prefix": ""
                                             }]
                                         }
                                     },
                                     "detail_type": ["Object Created"]
                                 },
                                 targets=[targets.SfnStateMachine(state_machine)])

