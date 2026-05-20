//+------------------------------------------------------------------+
//|                               DoubleDragon_Power_V5_Precision.mq5|
//|                                  核心：突破200/OCO/3min/极速追踪/盈利加仓|
//|                             修复说明：强化价格精度规范化，匹配实盘3位小数要求|
//+------------------------------------------------------------------+
#property copyright "Expert"
#property link      "https://m.jrjr.com/"
#property version   "5.01"
#property strict

#include <Trade\Trade.mqh>

//--- 基础参数
input double LotSize         = 0.1;       // 基础首单手数
input double AddLotSize      = 0.1;       // 盈利加仓手数
input int    Slippage        = 10;        // 滑点 (10点 = 0.1美元)
input int    MagicNumber     = 888888;    // EA识别码
input double DailyMaxLoss    = 300.0;     // 核心任务4：日亏损关机 (美元)

//--- 交易价格区间
input double PriceMin        = 4000.0;    // 交易区间底价
input double PriceMax        = 6000.0;    // 交易区间顶价

//--- 进场参数
input int    DistancePoints  = 200;       // 核心任务1：挂单距离 (200点 = 2.0美元)

//--- 追踪与止损参数
input int    InitialStopLoss = 10;        // 初始止损 (10点 = 0.1美元)
input int    TrailingStart   = 5;         // 获利 5 点激活追踪并触发加仓
input int    TrailingStop    = 2;         // 追踪回撤距离 (2点 = 0.02美元)
input int    TimeLimitMin    = 3;         // 核心任务3：持仓时间限制 (分钟)

//--- 全局变量
CTrade trade;
datetime DayStartTime;
double   InitialBalance;
bool     IsScaledIn = false; // 标记本轮交易是否已经加过仓

//+------------------------------------------------------------------+
//| 初始化                                                            |
//+------------------------------------------------------------------+
int OnInit()
{
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(Slippage);

    DayStartTime = iTime(_Symbol, PERIOD_D1, 0);
    InitialBalance = AccountInfoDouble(ACCOUNT_BALANCE);

    Print("--- EA Power V5 实盘修复版 已启动 ---");
    Print("当前品种精度: ", _Digits, " 位小数");
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| 主循环 (24小时)                                                   |
//+------------------------------------------------------------------+
void OnTick()
{
    // 1. 核心任务4：日损检查
    if(!CheckDailyLoss()) return;

    // 2. 价格区间检查
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    if(bid < PriceMin || bid > PriceMax) return;

    // 3. 核心管理：持仓管理（含加仓判断、时间止损、追踪止盈）
    HandlePositionsLogic();

    // 4. 核心任务1 & 2：挂单逻辑
    ManageOrders();
}

//+------------------------------------------------------------------+
//| 核心任务4：日损 300 自动关机                                        |
//+------------------------------------------------------------------+
bool CheckDailyLoss()
{
    if(iTime(_Symbol, PERIOD_D1, 0) != DayStartTime)
    {
        DayStartTime = iTime(_Symbol, PERIOD_D1, 0);
        InitialBalance = AccountInfoDouble(ACCOUNT_BALANCE);
    }
    double currentLoss = InitialBalance - AccountInfoDouble(ACCOUNT_EQUITY);
    if(currentLoss >= DailyMaxLoss)
    {
        Print("🛑 触发日损熔断！执行关机。");
        CloseAllPositions();
        CancelAllOrders();
        ExpertRemove();
        return false;
    }
    return true;
}

//+------------------------------------------------------------------+
//| 持仓综合管理 (含加仓、时间止损、极速追踪)                            |
//+------------------------------------------------------------------+
void HandlePositionsLogic()
{
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double point = _Point;
    int positionsCount = 0;

    for(int i=PositionsTotal()-1; i>=0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(PositionSelectByTicket(ticket))
        {
            if(PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            {
                positionsCount++;
                long posType = PositionGetInteger(POSITION_TYPE);
                double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
                double currentSL = PositionGetDouble(POSITION_SL);

                // --- A. 核心任务3：时间止损 ---
                long openTime = PositionGetInteger(POSITION_TIME);
                if(TimeCurrent() - openTime >= TimeLimitMin * 60)
                {
                    trade.PositionClose(ticket);
                    continue;
                }

                // --- B. 极速追踪与盈利加仓 ---
                if(posType == POSITION_TYPE_BUY)
                {
                    double profitPoints = (bid - openPrice) / point;
                    if(profitPoints >= TrailingStart)
                    {
                        if(positionsCount == 1 && !IsScaledIn)
                        {
                            // 修复：对加仓价格和止损价格进行严格的精度规范化
                            double buyPrice = NormalizeDouble(ask, _Digits);
                            double buySL = NormalizeDouble(bid - InitialStopLoss * point, _Digits);
                            if(trade.Buy(AddLotSize, _Symbol, buyPrice, buySL, 0, "Scale-In"))
                            {
                                IsScaledIn = true;
                            }
                        }
                        double newSL = NormalizeDouble(bid - TrailingStop * point, _Digits);
                        if(newSL > currentSL + point || currentSL == 0)
                            trade.PositionModify(ticket, newSL, 0);
                    }
                }
                else if(posType == POSITION_TYPE_SELL)
                {
                    double profitPoints = (openPrice - ask) / point;
                    if(profitPoints >= TrailingStart)
                    {
                        if(positionsCount == 1 && !IsScaledIn)
                        {
                            // 修复：规范化价格
                            double sellPrice = NormalizeDouble(bid, _Digits);
                            double sellSL = NormalizeDouble(ask + InitialStopLoss * point, _Digits);
                            if(trade.Sell(AddLotSize, _Symbol, sellPrice, sellSL, 0, "Scale-In"))
                            {
                                IsScaledIn = true;
                            }
                        }
                        double newSL = NormalizeDouble(ask + TrailingStop * point, _Digits);
                        if(newSL < currentSL - point || currentSL == 0)
                            trade.PositionModify(ticket, newSL, 0);
                    }
                }
            }
        }
    }
    if(positionsCount == 0) IsScaledIn = false;
}

//+------------------------------------------------------------------+
//| 核心任务1 & 2：OCO 突破挂单管理                                    |
//+------------------------------------------------------------------+
void ManageOrders()
{
    int ordersCount = 0;
    int positionsCount = 0;

    for(int i=PositionsTotal()-1; i>=0; i--)
        if(PositionSelectByTicket(PositionGetTicket(i)))
            if(PositionGetInteger(POSITION_MAGIC) == MagicNumber) positionsCount++;

    for(int i=OrdersTotal()-1; i>=0; i--)
        if(OrderGetInteger(ORDER_MAGIC) == MagicNumber) ordersCount++;

    if(positionsCount > 0)
    {
        if(ordersCount > 0) CancelAllOrders();
        return;
    }

    if(positionsCount == 0 && ordersCount == 0)
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
        double point = _Point;

        // 修复：对挂单价格、初始止损价格进行严格的精度规范化
        double buyStopPrice = NormalizeDouble(ask + DistancePoints * point, _Digits);
        double buyStopSL    = NormalizeDouble(buyStopPrice - InitialStopLoss * point, _Digits);

        double sellStopPrice = NormalizeDouble(bid - DistancePoints * point, _Digits);
        double sellStopSL     = NormalizeDouble(sellStopPrice + InitialStopLoss * point, _Digits);

        trade.BuyStop(LotSize, buyStopPrice, _Symbol, buyStopSL, 0, ORDER_TIME_GTC, 0, "Start_Order");
        trade.SellStop(LotSize, sellStopPrice, _Symbol, sellStopSL, 0, ORDER_TIME_GTC, 0, "Start_Order");
    }
}

//--- 清理函数
void CloseAllPositions()
{
    for(int i=PositionsTotal()-1; i>=0; i--)
        if(PositionSelectByTicket(PositionGetTicket(i)))
            if(PositionGetInteger(POSITION_MAGIC) == MagicNumber) trade.PositionClose(PositionGetTicket(i));
}

void CancelAllOrders()
{
    for(int i=OrdersTotal()-1; i>=0; i--)
        if(OrderSelect(OrderGetTicket(i)))
            if(OrderGetInteger(ORDER_MAGIC) == MagicNumber) trade.OrderDelete(OrderGetTicket(i));
}