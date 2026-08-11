port module VerifyTree exposing (main)

{-| Run a UI tree captured by the Windows host through the **real**
`EveOnline.ParseUserInterface`, and report what the bot would have been handed.

This exists because "the tree looks right" is not the standard this repo holds
things to, and because the failure issue #176 names -- a reader that decodes
wrongly and produces plausible nonsense rather than an error -- is invisible to
any check the reader marks its own homework with. The parser is the thing the
bots actually consult, so a tree that satisfies it is evidence of a different
kind from a tree that merely contains the right-looking strings.

Deliberately a `Platform.worker` fed over a port rather than an `elm repl`
expression, which is what `tools/macos-host/tests/prerequisites.py` uses. A real
tree is megabytes, and a repl takes its input as a source literal -- where
CLAUDE.md records Elm processing backslash escapes inside a triple-quoted string
and a fixture carrying a double quote decoding to `Nothing`, which reads exactly
like a parser that answered nothing. A port carries the string unaltered, so
that whole class of question does not arise.

Nothing here decides anything or asserts a threshold. It counts and it prints,
in the register the repo uses for a new instrument: the numbers are what a person
compares against the client on their screen.

-}

import EveOnline.MemoryReading
import EveOnline.ParseUserInterface exposing (ParsedUserInterface)
import Json.Encode


port treeIn : (String -> msg) -> Sub msg


port reportOut : Json.Encode.Value -> Cmd msg


type alias Model =
    ()


main : Program () Model String
main =
    Platform.worker
        { init = \_ -> ( (), Cmd.none )
        , update = \json model -> ( model, reportOut (report json) )
        , subscriptions = \_ -> treeIn identity
        }


report : String -> Json.Encode.Value
report json =
    case EveOnline.MemoryReading.decodeMemoryReadingFromString json of
        Err error ->
            Json.Encode.object
                [ ( "decoded", Json.Encode.bool False )
                , ( "error", Json.Encode.string (Debug.toString error) )
                ]

        Ok uiTree ->
            let
                parsed =
                    uiTree
                        |> EveOnline.ParseUserInterface.parseUITreeWithDisplayRegionFromUITree
                        |> EveOnline.ParseUserInterface.parseUserInterfaceFromUITree
            in
            Json.Encode.object
                [ ( "decoded", Json.Encode.bool True )
                , ( "nodes", Json.Encode.int (1 + EveOnline.MemoryReading.countDescendantsInUITreeNode uiTree) )
                , ( "nodesWithRegion"
                  , Json.Encode.int
                        (1 + EveOnline.ParseUserInterface.countDescendantsInUITreeNodeWithDisplayRegion parsed.uiTree)
                  )
                , ( "found", Json.Encode.object (whatWasParsed parsed) )
                , ( "displayTexts", Json.Encode.int (List.length (EveOnline.ParseUserInterface.getAllContainedDisplayTexts parsed.uiTree.uiNode)) )
                ]


{-| One entry per thing `ParsedUserInterface` carries, so an absent one is
visible as a zero rather than by not being mentioned. CLAUDE.md's own rule:
`Nothing` and `Just []` are different answers, and a report that prints only what
it found cannot tell them apart.
-}
whatWasParsed : ParsedUserInterface -> List ( String, Json.Encode.Value )
whatWasParsed parsed =
    let
        count name value =
            ( name, Json.Encode.int (List.length value) )

        present name value =
            ( name
            , Json.Encode.int
                (case value of
                    Just _ ->
                        1

                    Nothing ->
                        0
                )
            )
    in
    [ count "contextMenus" parsed.contextMenus
    , present "shipUI" parsed.shipUI
    , count "targets" parsed.targets
    , present "infoPanelContainer" parsed.infoPanelContainer
    , count "overviewWindows" parsed.overviewWindows
    , present "selectedItemWindow" parsed.selectedItemWindow
    , present "dronesWindow" parsed.dronesWindow
    , present "probeScannerWindow" parsed.probeScannerWindow
    , present "stationWindow" parsed.stationWindow
    , count "shipItemCards" parsed.shipItemCards
    , count "inventoryWindows" parsed.inventoryWindows
    , count "chatWindowStacks" parsed.chatWindowStacks
    , count "agentConversationWindows" parsed.agentConversationWindows
    , count "agentMissionInfoPanelEntries" parsed.agentMissionInfoPanelEntries
    , present "neocom" parsed.neocom
    , count "messageBoxes" parsed.messageBoxes
    , present "layerAbovemain" parsed.layerAbovemain
    , present "moduleButtonTooltip" parsed.moduleButtonTooltip
    ]
