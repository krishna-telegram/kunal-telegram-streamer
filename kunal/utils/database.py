import datetime
import motor.motor_asyncio


class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users
        self.bannedList = self.db.bannedList
        self.forwarded = self.db.forwarded_msgs

    def new_user(self, id):
        return dict(
            id=id,
            join_date=datetime.date.today().isoformat()
        )

    async def add_user(self, id):
        user = self.new_user(id)
        await self.col.insert_one(user)
        
    async def add_user_pass(self, id, ag_pass):
        await self.add_user(int(id))
        await self.col.update_one({'id': int(id)}, {'$set': {'ag_p': ag_pass}})
    
    async def get_user_pass(self, id):
        user_pass = await self.col.find_one({'id': int(id)})
        return user_pass.get("ag_p", None) if user_pass else None
    
    async def is_user_exist(self, id):
        user = await self.col.find_one({'id': int(id)})
        return True if user else False

    async def total_users_count(self):
        count = await self.col.count_documents({})
        return count

    async def get_all_users(self):
        all_users = self.col.find({})
        return all_users

    async def delete_user(self, user_id):
        await self.col.delete_many({'id': int(user_id)})
        
    async def ban_user(self , user_id):
        user = await self.bannedList.find_one({'banId' : int(user_id)})
        if user:
            return False
        else:
            await self.bannedList.insert_one({'banId' : int(user_id)})
            return True
        
    async def is_banned(self , user_id):
        user = await self.bannedList.find_one({'banId' : int(user_id)})
        return True if user else False
    
    async def is_unbanned(self , user_id):
        try : 
            if await self.bannedList.find_one({'banId' : int(user_id)}):
                await self.bannedList.delete_one({'banId' : int(user_id)})
                return True
            else:
                return False
        except Exception as e:
            e = f'Fᴀɪʟᴇᴅ ᴛᴏ ᴜɴʙᴀɴ.Rᴇᴀsᴏɴ : {e}'
            print(e)
            return e

    async def save_forwarded(self, source_chat_id, source_msg_id, target_msg_id, media_type=None, file_name=None, file_hash=None, file_size=0, mime_type=None):
        parsed_chat_id = int(source_chat_id) if str(source_chat_id).lstrip('-').isdigit() else str(source_chat_id)
        await self.forwarded.update_one(
            {
                'source_chat_id': parsed_chat_id,
                'source_msg_id': int(source_msg_id)
            },
            {
                '$set': {
                    'target_msg_id': int(target_msg_id),
                    'media_type': media_type,
                    'file_name': file_name,
                    'file_hash': file_hash,
                    'file_size': int(file_size or 0),
                    'mime_type': mime_type
                }
            },
            upsert=True
        )

    async def get_forwarded(self, source_chat_id, source_msg_id):
        parsed_chat_id = int(source_chat_id) if str(source_chat_id).lstrip('-').isdigit() else str(source_chat_id)
        doc = await self.forwarded.find_one({
            'source_chat_id': parsed_chat_id,
            'source_msg_id': int(source_msg_id)
        })
        return doc
