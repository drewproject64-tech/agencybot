import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import bot

class BotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        bot.DB_PATH = str(Path(self.tmp.name) / 'test.db')
        bot.ADMIN_USER_IDS = {99}
    def tearDown(self):
        self.tmp.cleanup()
    def user(self, uid=1):
        return NS(id=uid, full_name='Client', username='client', is_bot=False)
    def test_upsert_and_opt_out(self):
        bot.save_user(self.user()); bot.save_user(self.user())
        self.assertEqual(bot.recipients(), [1])
        bot.update_user_flag(1, subscribed=False)
        bot.save_user(self.user())
        self.assertEqual(bot.recipients(), [])
        conn=bot.db_connection()
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM users').fetchone()[0], 1)
        conn.close()
    def test_existing_leads_import(self):
        bot.create_lead(self.user(5)); bot.create_lead(self.user(5))
        self.assertEqual(bot.recipients(), [5])
    def test_admin_is_user_not_chat(self):
        self.assertFalse(bot.is_admin(NS(effective_user=self.user(1), effective_chat=NS(id=99))))
        self.assertTrue(bot.is_admin(NS(effective_user=self.user(99))))
    def test_unauthorized_callback(self):
        q=NS(data='admin:broadcast', answer=AsyncMock())
        ctx=NS(user_data={})
        result=asyncio.run(bot.admin_callback(NS(callback_query=q,effective_user=self.user()),ctx))
        self.assertTrue(result); self.assertEqual(ctx.user_data,{})
        q.answer.assert_awaited_once_with('Admin access only.',show_alert=True)
    def test_delivery_handles_blocked(self):
        from telegram.error import Forbidden
        bot.save_user(self.user(1)); bot.save_user(self.user(2))
        ctx=NS(bot=NS(copy_message=AsyncMock(side_effect=[Forbidden('blocked'),NS()]),send_message=AsyncMock()),application=NS(bot_data={'sending':True}))
        asyncio.run(bot.deliver_messages(ctx,{'target':'all','chat_id':99,'message_id':1},99))
        self.assertEqual(bot.recipients(),[2]); self.assertFalse(ctx.application.bot_data['sending'])
        self.assertIn('Sent: 1; failed: 1',ctx.bot.send_message.call_args.kwargs['text'])
    def test_stale_confirmation(self):
        q=NS(data='admin:send:old', answer=AsyncMock(),message=NS(reply_text=AsyncMock()))
        ctx=NS(user_data={'draft_token':'new','admin_draft':{'target':'all'}})
        asyncio.run(bot.admin_callback(NS(callback_query=q,effective_user=self.user(99)),ctx))
        self.assertIn('admin_draft',ctx.user_data)

if __name__ == '__main__': unittest.main()
