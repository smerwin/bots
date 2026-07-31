port module Main exposing (main)

{-| Thin wrapper turning a bot's `botMain : BotConfig State` into a runnable
`Platform.worker` program driven by JSON over ports. This module is NOT part
of the bot's own source -- it is added by the macOS host launcher before
compiling, so any bot written against `BotLab.BotInterface_To_Host_2023_02_06`
can be run without modification. The JSON shape used on the ports is this
wrapper's own convention (tag-object style, matching how
EveOnline.VolatileProcessInterface's hand-written codecs already do it) --
the host (Python) side must match it exactly; it does not need to match
whatever convention BotLab.exe's own Pine-based toolchain would use.

This is the older host interface, kept alongside `Main.elm` (2024_10_19)
because a bot's own source fixes which one it imports and the two are not
interchangeable. The difference that matters: 2023_02_06 has no
`WindowsInputRequest` task, so input is not a host-level task at all -- it
travels inside the volatile-process request as
`EveOnline.VolatileProcessInterface`'s `EffectSequenceOnWindow`, which the
Python host translates and executes.
-}

import Bot
import BotLab.BotInterface_To_Host_2023_02_06 as IH
import Json.Decode as D
import Json.Encode as E


port eventIn : (String -> msg) -> Sub msg


port responseOut : String -> Cmd msg


type Msg
    = EventIn String


type alias Model =
    { botState : Bot.State }


init : () -> ( Model, Cmd Msg )
init () =
    ( { botState = Bot.botMain.init }, Cmd.none )


update : Msg -> Model -> ( Model, Cmd Msg )
update (EventIn eventJson) model =
    case D.decodeString decodeBotEvent eventJson of
        Err err ->
            ( model
            , responseOut (E.encode 0 (E.object [ ( "DecodeError", E.string (D.errorToString err) ) ]))
            )

        Ok event ->
            let
                ( newState, response ) =
                    Bot.botMain.processEvent event model.botState
            in
            ( { model | botState = newState }
            , responseOut (E.encode 0 (encodeBotEventResponse response))
            )


main : Program () Model Msg
main =
    Platform.worker
        { init = init
        , update = update
        , subscriptions = \_ -> eventIn EventIn
        }



-- ENCODE: Elm -> JSON (Task tree the bot wants executed)


encodeBotEventResponse : IH.BotEventResponse -> E.Value
encodeBotEventResponse response =
    case response of
        IH.ContinueSession s ->
            E.object
                [ ( "ContinueSession"
                  , E.object
                        [ ( "statusText", E.string s.statusText )
                        , ( "startTasks", E.list encodeStartTask s.startTasks )
                        , ( "notifyWhenArrivedAtTime", encodeMaybe (\t -> E.object [ ( "timeInMilliseconds", E.int t.timeInMilliseconds ) ]) s.notifyWhenArrivedAtTime )
                        ]
                  )
                ]

        IH.FinishSession s ->
            E.object
                [ ( "FinishSession", E.object [ ( "statusText", E.string s.statusText ) ] ) ]


encodeStartTask : IH.StartTaskStructure -> E.Value
encodeStartTask t =
    E.object
        [ ( "taskId", E.string t.taskId )
        , ( "task", encodeTask t.task )
        ]


encodeTask : IH.Task -> E.Value
encodeTask task =
    case task of
        IH.CreateVolatileProcess s ->
            E.object [ ( "CreateVolatileProcess", E.object [ ( "programCode", E.string s.programCode ) ] ) ]

        IH.RequestToVolatileProcess s ->
            E.object [ ( "RequestToVolatileProcess", encodeRequestConsideringFocus s ) ]

        IH.ReleaseVolatileProcess s ->
            E.object [ ( "ReleaseVolatileProcess", E.object [ ( "processId", E.string s.processId ) ] ) ]

        IH.OpenWindowRequest s ->
            E.object [ ( "OpenWindowRequest", E.object [ ( "userGuide", E.string s.userGuide ) ] ) ]

        IH.InvokeMethodOnWindowRequest windowId methodOnWindow ->
            E.object
                [ ( "InvokeMethodOnWindowRequest"
                  , E.list identity [ E.string windowId, encodeMethodOnWindow methodOnWindow ]
                  )
                ]

        IH.RandomBytesRequest n ->
            E.object [ ( "RandomBytesRequest", E.int n ) ]


encodeRequestConsideringFocus : IH.RequestToVolatileProcessConsideringInputFocusStructure -> E.Value
encodeRequestConsideringFocus s =
    case s of
        IH.RequestNotRequiringInputFocus r ->
            E.object [ ( "RequestNotRequiringInputFocus", encodeRequestToVolatileProcess r ) ]

        IH.RequestRequiringInputFocus r ->
            E.object
                [ ( "RequestRequiringInputFocus"
                  , E.object
                        [ ( "request", encodeRequestToVolatileProcess r.request )
                        , ( "acquireInputFocus", E.object [ ( "maximumDelayMilliseconds", E.int r.acquireInputFocus.maximumDelayMilliseconds ) ] )
                        ]
                  )
                ]


encodeRequestToVolatileProcess : IH.RequestToVolatileProcessStructure -> E.Value
encodeRequestToVolatileProcess r =
    E.object
        [ ( "processId", E.string r.processId )
        , ( "request", E.string r.request )
        ]


encodeMethodOnWindow : IH.MethodOnWindow -> E.Value
encodeMethodOnWindow m =
    case m of
        IH.CloseWindowMethod ->
            E.object [ ( "CloseWindowMethod", E.null ) ]

        IH.ChromeDevToolsProtocolRuntimeEvaluateMethod p ->
            E.object
                [ ( "ChromeDevToolsProtocolRuntimeEvaluateMethod"
                  , E.object [ ( "expression", E.string p.expression ), ( "awaitPromise", E.bool p.awaitPromise ) ]
                  )
                ]

        IH.ReadFromWindowMethod ->
            E.object [ ( "ReadFromWindowMethod", E.null ) ]


encodeMaybe : (a -> E.Value) -> Maybe a -> E.Value
encodeMaybe enc maybe =
    case maybe of
        Nothing ->
            E.null

        Just a ->
            enc a



-- DECODE: JSON -> Elm (events and task results coming from the host)


decodeBotEvent : D.Decoder IH.BotEvent
decodeBotEvent =
    D.map2 IH.BotEvent
        (D.field "timeInMilliseconds" D.int)
        (D.field "eventAtTime" decodeBotEventAtTime)


decodeBotEventAtTime : D.Decoder IH.BotEventAtTime
decodeBotEventAtTime =
    D.oneOf
        [ D.field "TimeArrivedEvent" (D.succeed IH.TimeArrivedEvent)
        , D.field "BotSettingsChangedEvent" D.string |> D.map IH.BotSettingsChangedEvent
        , D.field "SessionDurationPlannedEvent"
            (D.map (\t -> { timeInMilliseconds = t }) (D.field "timeInMilliseconds" D.int))
            |> D.map IH.SessionDurationPlannedEvent
        , D.field "TaskCompletedEvent" decodeCompletedTask |> D.map IH.TaskCompletedEvent
        ]


decodeCompletedTask : D.Decoder IH.CompletedTaskStructure
decodeCompletedTask =
    D.map2 IH.CompletedTaskStructure
        (D.field "taskId" D.string)
        (D.field "taskResult" decodeTaskResult)


decodeTaskResult : D.Decoder IH.TaskResultStructure
decodeTaskResult =
    D.oneOf
        [ D.field "CreateVolatileProcessResponse" (decodeResult decodeCreateVolatileProcessError decodeCreateVolatileProcessComplete)
            |> D.map IH.CreateVolatileProcessResponse
        , D.field "RequestToVolatileProcessResponse" (decodeResult decodeRequestToVolatileProcessError decodeRequestToVolatileProcessComplete)
            |> D.map IH.RequestToVolatileProcessResponse
        , D.field "OpenWindowResponse" (decodeResult D.string decodeOpenWindowSuccess)
            |> D.map IH.OpenWindowResponse
        , D.field "InvokeMethodOnWindowResponse"
            (D.map2 Tuple.pair
                (D.index 0 D.string)
                (D.index 1 (decodeResult decodeInvokeMethodOnWindowError decodeInvokeMethodOnWindowResult))
            )
            |> D.map (\( w, r ) -> IH.InvokeMethodOnWindowResponse w r)
        , D.field "RandomBytesResponse" (D.list D.int) |> D.map IH.RandomBytesResponse
        , D.field "CompleteWithoutResult" (D.succeed IH.CompleteWithoutResult)
        ]


decodeCreateVolatileProcessError : D.Decoder IH.CreateVolatileProcessErrorStructure
decodeCreateVolatileProcessError =
    D.map (\s -> { exceptionToString = s }) (D.field "exceptionToString" D.string)


decodeCreateVolatileProcessComplete : D.Decoder IH.CreateVolatileProcessComplete
decodeCreateVolatileProcessComplete =
    D.map (\s -> { processId = s }) (D.field "processId" D.string)


decodeRequestToVolatileProcessError : D.Decoder IH.RequestToVolatileProcessError
decodeRequestToVolatileProcessError =
    D.oneOf
        [ D.field "ProcessNotFound" (D.succeed IH.ProcessNotFound)
        , D.field "FailedToAcquireInputFocus" (D.succeed IH.FailedToAcquireInputFocus)
        ]


decodeRequestToVolatileProcessComplete : D.Decoder IH.RequestToVolatileProcessComplete
decodeRequestToVolatileProcessComplete =
    D.map4 IH.RequestToVolatileProcessComplete
        (D.maybe (D.field "exceptionToString" D.string))
        (D.maybe (D.field "returnValueToString" D.string))
        (D.field "durationInMilliseconds" D.int)
        (D.field "acquireInputFocusDurationMilliseconds" D.int)


decodeOpenWindowSuccess : D.Decoder IH.OpenWindowSuccess
decodeOpenWindowSuccess =
    D.map2 IH.OpenWindowSuccess
        (D.field "windowId" D.string)
        (D.field "osProcessId" D.string)


decodeInvokeMethodOnWindowError : D.Decoder IH.InvokeMethodOnWindowError
decodeInvokeMethodOnWindowError =
    D.oneOf
        [ D.field "WindowNotFoundError" (D.map (\ids -> { windowsIds = ids }) (D.field "windowsIds" (D.list D.string)))
            |> D.map IH.WindowNotFoundError
        , D.field "MethodNotAvailableError" (D.succeed IH.MethodNotAvailableError)
        , D.field "ReadFromWindowError" D.string |> D.map IH.ReadFromWindowError
        ]


decodeInvokeMethodOnWindowResult : D.Decoder IH.InvokeMethodOnWindowResult
decodeInvokeMethodOnWindowResult =
    D.oneOf
        [ D.field "ChromeDevToolsProtocolRuntimeEvaluateMethodResult"
            (decodeResult D.string (D.map (\s -> { returnValueJsonSerialized = s }) (D.field "returnValueJsonSerialized" D.string)))
            |> D.map IH.ChromeDevToolsProtocolRuntimeEvaluateMethodResult
        , D.field "ReadFromWindowMethodResult" decodeReadFromWindowComplete |> D.map IH.ReadFromWindowMethodResult
        , D.field "InvokeMethodOnWindowResultWithoutValue" (D.succeed IH.InvokeMethodOnWindowResultWithoutValue)
        ]


decodeReadFromWindowComplete : D.Decoder IH.ReadFromWindowCompleteStruct
decodeReadFromWindowComplete =
    D.map6
        (\readingId windowText windowRect clientRect clientRectLeftUpperToScreen imageData ->
            { readingId = readingId
            , windowText = windowText
            , windowRect = windowRect
            , clientRect = clientRect
            , clientRectLeftUpperToScreen = clientRectLeftUpperToScreen
            , imageData = imageData
            }
        )
        (D.field "readingId" D.string)
        (D.field "windowText" D.string)
        (D.field "windowRect" decodeWinApiRect)
        (D.field "clientRect" decodeWinApiRect)
        (D.field "clientRectLeftUpperToScreen" decodeWinApiPoint)
        (D.field "imageData" decodeImageData)


decodeWinApiRect : D.Decoder IH.WinApiRectStruct
decodeWinApiRect =
    D.map4 IH.WinApiRectStruct
        (D.field "left" D.int)
        (D.field "top" D.int)
        (D.field "right" D.int)
        (D.field "bottom" D.int)


decodeWinApiPoint : D.Decoder IH.WinApiPointStruct
decodeWinApiPoint =
    D.map2 IH.WinApiPointStruct
        (D.field "x" D.int)
        (D.field "y" D.int)


decodeImageData : D.Decoder IH.ImageDataFromReadingCompleteStruct
decodeImageData =
    D.map3 IH.ImageDataFromReadingCompleteStruct
        (D.field "screenshotCrops_original" (D.list decodeImageCrop))
        (D.field "screenshotCrops_binned_2x2" (D.list decodeImageCrop))
        (D.field "screenshotCrops_binned_4x4" (D.list decodeImageCrop))


decodeImageCrop : D.Decoder IH.ImageCrop
decodeImageCrop =
    D.map3 IH.ImageCrop
        (D.field "offset" decodeWinApiPoint)
        (D.field "widthPixels" D.int)
        (D.field "pixelsString" D.string)


decodeResult : D.Decoder e -> D.Decoder a -> D.Decoder (Result e a)
decodeResult errDecoder okDecoder =
    D.oneOf
        [ D.field "Err" errDecoder |> D.map Err
        , D.field "Ok" okDecoder |> D.map Ok
        ]
