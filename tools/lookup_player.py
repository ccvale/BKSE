'''Look up which NBA team a player is on.'''

import json
import urllib.parse
import urllib.request

from langchain_core.tools import tool
from loguru import logger

SEARCH = 'https://site.api.espn.com/apis/common/v3/search'

@tool
def lookup_player(name: str) -> str:
    '''Look up which NBA team a player is on right now.

    Call this when the user names a player that they want to see play at the Barclays Center. Pass their words. Do not guess the team.
    If the player is not on the Nets, you can help find them tickets to watch them play the Nets at the Barclays Center.
    '''
    name = name.strip()
    if not name: # edge case just in case tool called without a name
        return 'No player name was given.'
    url = SEARCH + '?' + urllib.parse.urlencode({'query': name, 'limit': 5, 'type': 'player'}) # ESPN API search endpoint
    request = urllib.request.Request(url, headers={'User-Agent': 'bkse'}) # request with a user agent to avoid being blocked (edge case encountered)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            items = json.load(response).get('items') or [] # load the response as JSON and get the items
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning('Player lookup failed for {}: {}', name, exc)
        return 'Player lookup is unavailable right now.'
    matches = [] # list to store the matches
    for item in items:
        if item.get('league') != 'nba' or not item.get('isActive'): # if the item is not in the NBA or is not active, skip
            continue
        teams = item.get('teamRelationships') or [] # get the team relationships
        if not teams: # if there are no teams, skip
            continue
        team = (teams[0].get('core') or {}).get('displayName') # get the display name of the team
        if team: # if the team is not None, add the player and team to the matches list
            matches.append(f'{item.get("displayName")} plays for the {team}')
    if not matches: # if there are no matches, return a message saying no active NBA player was found
        return f'No active NBA player matched {name}.'
    text = matches[0] + '.' # the first match is the most likely match
    if len(matches) > 1:
        text += ' Other matches: ' + '; '.join(matches[1:]) + '.' # if there are other matches, add them to the text (not sure when this would be the case)
    return text


if __name__ == '__main__':
    randle = lookup_player.invoke({'name': 'Julius Randle'})
    nobody = lookup_player.invoke({'name': 'zzzz-not-a-player'})
    assert 'plays for the' in randle
    assert 'No active NBA player' in nobody
    logger.info(randle)
    logger.info(nobody)
