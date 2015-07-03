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

class ChallengeTest extends BrowserTest
  names: ['ChallengeTest', 'challenge']
  description: "Tests the ability to create a game"
  numTests: 6

  testBody: (test) =>
    a_email = 'a@here.com'
    b_email = 'b@here.com'
    c_email = 'c@here.com'
    d_email = 'd@here.com'
    a_link = null
    a_link_target = null

    casper.thenOpen serverUrl, =>
      test.assertExists '#challenge-link'
    casper.thenClick '#challenge-link', ->
      form_values =
        'input[name="a_email"]' : a_email
        'input[name="b_email"]' : b_email
        'input[name="c_email"]' : c_email
        'input[name="d_email"]' : d_email
      # The final 'false' argument means that the form is not submitted.
      @fillSelectors 'form', form_values, false

    casper.thenClick '#send_challenge', =>
      test.assertExists '#a_secret'
      test.assertExists '#b_secret'
      test.assertExists '#c_secret'
      test.assertExists '#d_secret'
      a_link_target = casper.getElementAttribute '#a_player_link', 'href'

    casper.thenOpen serverUrl, =>
      casper.thenOpen ('http://127.0.0.1:5000' + a_link_target), =>
        test.assertExists '.game-log'

registerTest new ChallengeTest



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
