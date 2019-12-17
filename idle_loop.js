/*
current, lastidle = first, first
// loopTo maybe better name

oncreate(item):
  if not lastidle:
    lastidle = current
    item.play()

onpause:
  if current is complete:
    if current is last:
      if lastidle:
        lastidle.play()
        lastidle = null

ontrash(item):
  if item == current:
    current = current.nextsibling
    if item == lastidle:
      lastidle = lastidle.nextsibling
*/
