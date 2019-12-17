
// * TODO update edit list
// * TODO update move item
// * TODO update vote assign
// * TODO what happens on update if list/item editor is open?

/* (workaround applied to ui_test
ON +listling rtu ...
(ON greeting-test +micro hello UI test fails on post greeting on saucelabs)
errormsg
cause: saucelabs buffers SSE
(eigentlich DEPENDS ON sauce issue, aber zu großer act)

https://support.saucelabs.com/hc/en-us/articles/115002212447-Unable-to-Reach-Application-on-localhost-for-Tests-Run-on-Safari-8-and-9-and-Edge
if edge will someday proxy localhost url -> no more workaround needed
URL = localhost:8079 (something not using saucelabs localhostproxy)
*/
