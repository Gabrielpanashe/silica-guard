import { View, Text, TouchableOpacity, ScrollView, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Modal } from '@ant-design/react-native';
import { Feather } from '@expo/vector-icons';
import { ui, fonts } from '../theme';

/**
 * NotificationsSheet — the bell's bottom sheet (2 October 2026). Items come
 * from services/notificationsFeed.js (built on-device until the backend
 * notifications pipeline exists). Ant Design's popup Modal handles the
 * slide-up, mask and dismiss gesture.
 *
 *   visible   bool
 *   items     notificationsFeed item[]
 *   onClose   () => void
 *   onAction  (item) => void
 */
const TONES = {
  danger:  { colour: ui.refer,   bg: ui.referSoft,   icon: 'alert-triangle' },
  warning: { colour: ui.watch,   bg: ui.watchSoft,   icon: 'clock' },
  info:    { colour: ui.primary, bg: ui.primarySoft, icon: 'calendar' },
};

export default function NotificationsSheet({ visible, items, onClose, onAction }) {
  const insets = useSafeAreaInsets();
  return (
    <Modal popup visible={visible} onClose={onClose} animationType="slide-up" maskClosable>
      <View style={[s.sheet, { paddingBottom: insets.bottom + 16 }]}>
        <View style={s.handle} />
        <View style={s.header}>
          <Text style={s.title}>Notifications</Text>
          <TouchableOpacity onPress={onClose} hitSlop={8}>
            <Text style={s.close}>Done</Text>
          </TouchableOpacity>
        </View>

        <ScrollView style={{ maxHeight: 420 }}>
          {items.length === 0 ? (
            <View style={s.empty}>
              <Feather name="bell-off" size={28} color={ui.tabInactive} />
              <Text style={s.emptyTitle}>You're all caught up</Text>
              <Text style={s.emptyBody}>
                Overdue referrals, upcoming visits and unsynced screenings will show up here.
              </Text>
            </View>
          ) : (
            items.map((item) => {
              const t = TONES[item.tone] || TONES.info;
              return (
                <TouchableOpacity
                  key={item.id}
                  style={s.item}
                  onPress={() => onAction(item)}
                  activeOpacity={0.75}
                >
                  <View style={[s.iconTile, { backgroundColor: t.bg }]}>
                    <Feather name={item.kind === 'sync' ? 'refresh-cw' : t.icon} size={18} color={t.colour} />
                  </View>
                  <View style={{ flex: 1, gap: 2 }}>
                    <Text style={s.itemTitle}>{item.title}</Text>
                    <Text style={s.itemBody}>{item.body}</Text>
                  </View>
                  <Feather name="chevron-right" size={18} color={ui.tabInactive} />
                </TouchableOpacity>
              );
            })
          )}
        </ScrollView>

        <Text style={s.footnote}>Built from today's data on this phone.</Text>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  sheet: { backgroundColor: ui.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingHorizontal: 20, paddingTop: 10 },
  handle: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: ui.border, marginBottom: 12 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  title: { fontFamily: fonts.bold, fontSize: 17, color: ui.ink },
  close: { fontFamily: fonts.semibold, fontSize: 14, color: ui.primary },
  item: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: ui.border,
  },
  iconTile: { width: 38, height: 38, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  itemTitle: { fontFamily: fonts.semibold, fontSize: 14, color: ui.ink },
  itemBody: { fontFamily: fonts.medium, fontSize: 12, color: ui.muted },
  empty: { alignItems: 'center', paddingVertical: 28, gap: 8 },
  emptyTitle: { fontFamily: fonts.bold, fontSize: 15, color: ui.ink },
  emptyBody: { fontFamily: fonts.medium, fontSize: 12, color: ui.muted, textAlign: 'center', paddingHorizontal: 20 },
  footnote: { fontFamily: fonts.medium, fontSize: 11, color: ui.tabInactive, textAlign: 'center', marginTop: 12 },
});
