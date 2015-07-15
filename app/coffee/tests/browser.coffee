# compute server url from arguments

defaultHost = "http://localhost"
host = casper.cli.options['host'] or defaultHost
port = casper.cli.options['port'] or
  if host is defaultHost then "5000" else "80"

portString = if port == "80" or port == 80 then "" else ":#{port}"

unless (host.match /localhost/) or (host.match /staging/)
  casper.die "Server url contains neither 'localhost' nor 'staging', aborting"

serverUrl = "#{host}#{portString}"
casper.echo "Testing against server at #{serverUrl}"

debug_dump_html = () ->
  "Occasionally can be useful during debugging just to dump the current HTML."
  casper.echo (casper.getHTML())


# test inventory management

testObjectsByName = {}
allTestObjects = []

registerTest = (test) ->
  allTestObjects.push test
  for name in test.names
    testObjectsByName[name] = test

runTest = (name) ->
  test = testObjectsByName[name]
  test.run()

runAll = ->
  for test in allTestObjects
    test.run()

# test suites
class BrowserTest
  # An abstract base class for our browser tests
  #
  # Instances should define the following properties:
  #
  # * testBody: called by `run` below to execute the test
  # * names: array of names by which a caller can identify this test (with the
  #          `--single` command line option)
  # * description
  # * numTests: expected number of assertions

  run: =>
    casper.test.begin @description, @numTests, (test) =>
      casper.start()
      @testBody(test)
      casper.then ->
        test.done()

  names: []
  description: 'This class needs a description'
  numTests: 0

class CompleteRandomGameTest extends BrowserTest
  names: ['CompleteGame', 'randomgame']
  description: "A full run of creating and completing a game, with random moves"
  numTests: 7

  testBody: (test) =>
    neutral_game_address = null
    game_addresses = {a: null, b: null, c:null, d:null}

    casper.thenOpen serverUrl, =>
      test.assertExists '#start-new-game-link'
    casper.thenClick '#start-new-game-link', ->
      neutral_game_address = casper.getCurrentUrl()
      for player in ['a', 'b', 'c', 'd']
        test.assertExists ('#claim-player-' + player)

    casper.then =>
      claim_player = (player) ->
        casper.thenOpen neutral_game_address, =>
          casper.echo 'This is player----: ' + player
          casper.thenClick ('#claim-player-' + player), =>
            casper.echo 'This is player: ' + player
            game_addresses[player] = casper.getCurrentUrl()
      for player in ['a', 'b', 'c', 'd']
        claim_player player

    game_finished = false
    internal_server_error = false
    casper.thenOpen serverUrl, =>
      rotateThroughPlayers = () =>
        for player in ['a', 'b', 'c', 'd']
          casper.thenOpen game_addresses[player], =>
            if casper.exists '.playable-move a'
              # We wish to collect a *random* link from the playable moves,
              # we could just have `casper.thenClick '.playable-move a'` but
              # this would also select the first available move, which would
              # likely lead to missing some test scenarios. In particular you
              # would only ever guard whilst guessing the princess.
              move_link = casper.evaluate () ->
                links = document.querySelectorAll('.playable-move a')
                links[Math.floor(Math.random() * links.length)]
              casper.open move_link.href
            h1_text = casper.fetchText 'h1'
            if (h1_text.indexOf 'Internal Server Error') isnt -1
              internal_server_error = true
            if casper.exists '.game-winner'
              game_finished = true
        casper.then ->
          if not game_finished and not internal_server_error
            rotateThroughPlayers()
      casper.then ->
        rotateThroughPlayers()
      # Just to check that we are really finishing because the game is finished
      # and not because of some error.
      casper.then ->
        test.assertTrue game_finished
        test.assertFalse internal_server_error

registerTest new CompleteRandomGameTest


# helper functions

# run it

if casper.cli.has("single")
  runTest casper.cli.options['single']
else
  runAll()

casper.run ->
  casper.log "shutting down..."
  casper.open 'http://localhost:5000/shutdown',
    method: 'post'
