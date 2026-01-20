#!/usr/bin/env python3
"""
VK API Wrapper
Wrapper untuk VK API methods yang dibutuhkan untuk automation
"""

import requests
import time
from typing import Dict, List, Optional, Union
from vk_errors import get_error_description, is_skippable_error, is_rate_limit_error


class VKApiError(Exception):
    """VK API Error Exception"""
    def __init__(self, message, error_code=None):
        super().__init__(message)
        self.error_code = error_code


class VKApi:
    def __init__(self, access_token: str, user_id: str, alternative_token: str = None, version: str = "5.131"):
        """
        Initialize VK API wrapper with dual-token support

        Args:
            access_token: Primary VK OAuth access token
            user_id: VK user ID
            alternative_token: Alternative token for fallback (optional)
            version: VK API version (default: 5.131)
        """
        self.access_token = access_token
        self.alternative_token = alternative_token
        self.current_token = access_token
        self.user_id = user_id
        self.version = version
        self.base_url = "https://api.vk.com/method/"
        self.last_request_time = 0
        self.request_delay = 0.34
        self.token_switched = False

    def _wait_rate_limit(self):
        """Wait to respect VK API rate limit"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.request_delay:
            sleep_time = self.request_delay - time_since_last

            for _ in range(int(sleep_time * 10)):
                try:
                    from automation_core import STOP_FLAG
                    if STOP_FLAG:
                        break
                except:
                    pass
                time.sleep(0.1)

        self.last_request_time = time.time()

    def _switch_to_alternative_token(self):
        """Switch to alternative token if available"""
        if self.alternative_token and not self.token_switched:
            print(f"\n⚠ Switching to alternative VK token...")
            self.current_token = self.alternative_token
            self.token_switched = True
            return True
        return False

    def _call_method(self, method: str, params: Dict = None, retry_with_alt: bool = True) -> Dict:
        """
        Call VK API method with automatic alternative token fallback

        Args:
            method: VK API method name (e.g., 'friends.add')
            params: Method parameters
            retry_with_alt: Whether to retry with alternative token on error (default: True)

        Returns:
            API response data

        Raises:
            VKApiError: If API returns error on both tokens
        """
        if params is None:
            params = {}

        params['access_token'] = self.current_token
        params['v'] = self.version

        self._wait_rate_limit()

        url = f"{self.base_url}{method}"

        try:
            response = requests.post(url, data=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if 'error' in data:
                error = data['error']
                error_code = error.get('error_code')
                error_msg = error.get('error_msg')



                if error_code == 15 and retry_with_alt and self._switch_to_alternative_token():
                    return self._call_method(method, params, retry_with_alt=False)

                raise VKApiError(f"VK API Error {error_code}: {error_msg}")

            return data.get('response', {})

        except requests.exceptions.RequestException as e:
            raise VKApiError(f"Request failed: {e}")



    def friends_add(self, user_id: Union[int, str], text: str = None) -> Dict:
        """
        Add friend or send friend request

        Args:
            user_id: Target user ID
            text: Optional message text

        Returns:
            API response (1 = request sent, 2 = request approved, 4 = request resent)
        """
        params = {'user_id': user_id}
        if text:
            params['text'] = text
        return self._call_method('friends.add', params)

    def friends_delete(self, user_id: Union[int, str]) -> Dict:
        """
        Delete friend (DO NOT USE for vkserfing tasks!)

        Args:
            user_id: Target user ID

        Returns:
            API response
        """
        params = {'user_id': user_id}
        print(f"[VK API] Deleting friend: {user_id}")
        return self._call_method('friends.delete', params)



    def groups_join(self, group_id: Union[int, str]) -> Dict:
        """
        Join group or public page

        Args:
            group_id: Group ID (without minus sign)

        Returns:
            API response (1 = success)
        """

        if isinstance(group_id, str) and group_id.startswith('-'):
            group_id = group_id[1:]

        params = {'group_id': group_id}
        return self._call_method('groups.join', params)

    def groups_leave(self, group_id: Union[int, str]) -> Dict:
        """
        Leave group (DO NOT USE for vkserfing tasks!)

        Args:
            group_id: Group ID

        Returns:
            API response (1 = success)
        """
        if isinstance(group_id, str) and group_id.startswith('-'):
            group_id = group_id[1:]

        params = {'group_id': group_id}
        print(f"[VK API] Leaving group: {group_id}")
        return self._call_method('groups.leave', params)

    def groups_is_member(self, group_id: Union[int, str], user_id: Union[int, str] = None) -> bool:
        """
        Check if user is member of group

        Args:
            group_id: Group ID
            user_id: User ID (default: current user)

        Returns:
            True if member, False otherwise
        """
        if isinstance(group_id, str) and group_id.startswith('-'):
            group_id = group_id[1:]

        params = {'group_id': group_id}
        if user_id:
            params['user_id'] = user_id

        result = self._call_method('groups.isMember', params)
        return bool(result)



    def likes_add(self, owner_id: Union[int, str], item_id: Union[int, str],
                  item_type: str = 'post') -> Dict:
        """
        Add like to post/photo/video/comment

        Args:
            owner_id: Owner ID (user or group)
            item_id: Item ID
            item_type: Type of item (post, photo, video, comment, note, market, etc.)

        Returns:
            API response with likes count
        """
        params = {
            'type': item_type,
            'owner_id': owner_id,
            'item_id': item_id
        }
        return self._call_method('likes.add', params)

    def likes_delete(self, owner_id: Union[int, str], item_id: Union[int, str],
                     item_type: str = 'post') -> Dict:
        """
        Remove like (DO NOT USE for vkserfing tasks!)

        Args:
            owner_id: Owner ID
            item_id: Item ID
            item_type: Type of item

        Returns:
            API response
        """
        params = {
            'type': item_type,
            'owner_id': owner_id,
            'item_id': item_id
        }

        print(f"[VK API] Removing like: {owner_id}_{item_id} ({item_type})")
        return self._call_method('likes.delete', params)

    def likes_is_liked(self, owner_id: Union[int, str], item_id: Union[int, str],
                       item_type: str = 'post') -> bool:
        """
        Check if item is liked by current user

        Args:
            owner_id: Owner ID
            item_id: Item ID
            item_type: Type of item

        Returns:
            True if liked, False otherwise
        """
        params = {
            'type': item_type,
            'owner_id': owner_id,
            'item_id': item_id
        }

        result = self._call_method('likes.isLiked', params)
        return bool(result.get('liked', 0))



    def polls_vote(self, poll_id: int, answer_ids: list, owner_id: int) -> Dict:
        """
        Vote in a poll

        Args:
            poll_id: Poll ID
            answer_ids: List of answer IDs to vote for
            owner_id: Poll owner ID

        Returns:
            API response
        """
        params = {
            'poll_id': poll_id,
            'answer_ids': ','.join(map(str, answer_ids)),
            'owner_id': owner_id
        }

        print(f"[VK API] Voting in poll {poll_id} (answers: {answer_ids})")
        return self._call_method('polls.addVote', params)



    def video_view(self, video_id: str, owner_id: int) -> Dict:
        """
        Register video view

        Args:
            video_id: Video ID
            owner_id: Video owner ID

        Returns:
            API response
        """
        params = {
            'video_id': video_id,
            'owner_id': owner_id
        }

        print(f"[VK API] Viewing video {owner_id}_{video_id}")


        return self._call_method('video.get', params)



    def wall_repost(self, object_id: str, message: str = None, group_id: int = None) -> Dict:
        """
        Repost (share) a post

        Args:
            object_id: Post ID in format 'owner_id_post_id' (e.g., '-12345_67890')
            message: Optional message to add
            group_id: Optional group ID to repost to

        Returns:
            API response with post info
        """
        params = {'object': object_id}

        if message:
            params['message'] = message

        if group_id:
            params['group_id'] = group_id

        print(f"[VK API] Reposting: {object_id}")
        return self._call_method('wall.repost', params)

    def wall_delete(self, post_id: int, owner_id: int = None) -> Dict:
        """
        Delete post from wall (DO NOT USE for reposts!)

        Args:
            post_id: Post ID
            owner_id: Owner ID (default: current user)

        Returns:
            API response (1 = success)
        """
        params = {'post_id': post_id}

        if owner_id:
            params['owner_id'] = owner_id

        print(f"[VK API] Deleting post: {post_id}")
        return self._call_method('wall.delete', params)



    def utils_resolve_screen_name(self, screen_name: str) -> Dict:
        """
        Resolve screen name (short name) to ID

        Args:
            screen_name: Screen name (e.g., 'durov', 'club12345')

        Returns:
            Dict with 'type' and 'object_id'
        """
        params = {'screen_name': screen_name}
        return self._call_method('utils.resolveScreenName', params)

    def parse_vk_url(self, url: str) -> Dict:
        """
        Parse VK URL and extract object info

        Args:
            url: VK URL (e.g., 'https://vk.com/wall-12345_67890')

        Returns:
            Dict with object type and IDs
        """

        if 'vk.com/' in url:
            url = url.split('vk.com/')[-1]


        url = url.split('?')[0]

        result = {
            'type': None,
            'owner_id': None,
            'item_id': None,
            'screen_name': None
        }


        if url.startswith('wall'):
            parts = url.replace('wall', '').split('_')
            if len(parts) == 2:
                result['type'] = 'wall'
                result['owner_id'] = parts[0]
                result['item_id'] = parts[1]
                return result


        if url.startswith(('club', 'public')):
            group_id = url.replace('club', '').replace('public', '')
            result['type'] = 'group'
            result['owner_id'] = f"-{group_id}"
            return result


        if url.startswith('id'):
            user_id = url.replace('id', '')
            result['type'] = 'user'
            result['owner_id'] = user_id
            return result


        result['type'] = 'screen_name'
        result['screen_name'] = url
        return result



    def users_get(self, user_ids: Union[int, str, List] = None, fields: str = None) -> List[Dict]:
        """
        Get user info

        Args:
            user_ids: User ID(s) or screen name(s)
            fields: Additional fields to return

        Returns:
            List of user info dicts
        """
        params = {}

        if user_ids:
            if isinstance(user_ids, list):
                user_ids = ','.join(map(str, user_ids))
            params['user_ids'] = user_ids

        if fields:
            params['fields'] = fields

        return self._call_method('users.get', params)


def extract_token_from_url(oauth_url: str) -> Dict[str, str]:
    """
    Extract access token, user_id, and expires_in from OAuth URL

    Args:
        oauth_url: OAuth redirect URL from VK

    Returns:
        Dict with access_token, user_id, expires_in

    Example:
        >>> url = "https://oauth.vk.com/blank.html#access_token=vk1.a.xxx&expires_in=0&user_id=123"
        >>> extract_token_from_url(url)
        {'access_token': 'vk1.a.xxx', 'expires_in': '0', 'user_id': '123'}
    """
    result = {
        'access_token': None,
        'user_id': None,
        'expires_in': None
    }


    if '#' in oauth_url:
        fragment = oauth_url.split('#')[1]
    else:
        fragment = oauth_url


    params = {}
    for param in fragment.split('&'):
        if '=' in param:
            key, value = param.split('=', 1)
            params[key] = value

    result['access_token'] = params.get('access_token')
    result['user_id'] = params.get('user_id')
    result['expires_in'] = params.get('expires_in')

    return result


if __name__ == "__main__":

    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python3 vk_api_wrapper.py <oauth_url>")
        print("\nExample:")
        print("  python3 vk_api_wrapper.py 'https://oauth.vk.com/blank.html#access_token=...&user_id=...'")
        sys.exit(1)

    oauth_url = sys.argv[1]
    token_data = extract_token_from_url(oauth_url)

    print("Extracted Token Data:")
    print(json.dumps(token_data, indent=2))

    if token_data['access_token']:
        print("\n[SUCCESS] Token extracted successfully!")
        print(f"User ID: {token_data['user_id']}")
        print(f"Expires: {'Never' if token_data['expires_in'] == '0' else token_data['expires_in'] + ' seconds'}")
